from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models import Order, OrderStatus, OrderSide, OrderType
from app.schemas import OrderCreate
from app.services import kafka_producer, wallet_client, exchange_client
from app.services.exchange_ws_consumer import consumer as ws_consumer, ExchangeWsError
from app.services import fee_policy, platform_fees


async def create_order(db: AsyncSession, user_id: int, data: OrderCreate) -> Order:
    # For BUY orders, estimate cost and reserve funds in wallet service
    reserved = False
    reference_id = None
    platform_fee_rate = await fee_policy.get_current_fee_rate(db)

    reserve_price = data.price if data.price is not None else data.market_price_estimate
    if data.side == OrderSide.BUY and reserve_price is not None:
        estimated_trade_value = platform_fees.calculate_trade_value(data.quantity, reserve_price)
        estimated_platform_fee = platform_fees.calculate_platform_fee(
            data.quantity,
            reserve_price,
            platform_fee_rate,
        )
        estimated_cost = estimated_trade_value + estimated_platform_fee
        reference_id = f"order-{user_id}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        try:
            await wallet_client.reserve_funds(user_id, float(estimated_cost), reference_id)
            reserved = True
        except wallet_client.WalletError as e:
            raise HTTPException(status_code=402, detail=str(e))

    order = Order(
        user_id=user_id,
        symbol=data.symbol,
        side=data.side,
        order_type=data.order_type,
        quantity=data.quantity,
        price=data.price,
        status=OrderStatus.PENDING,
        wallet_reference_id=reference_id,
        platform_fee_rate=platform_fee_rate,
    )
    db.add(order)
    await db.flush()

    try:
        exchange_order_id = str(uuid4())
        ws_payload = {
            "order_id": exchange_order_id,
            "platform_user_id": str(user_id),
            "instrument_type": "STOCK",
            "instrument_id": data.symbol,
            "order_type": data.order_type.value,
            "side": data.side.value,
            "quantity": data.quantity,
        }
        if data.order_type == OrderType.LIMIT:
            ws_payload["limit_price"] = float(data.price)
            ws_payload["expires_at"] = (
                datetime.now(timezone.utc) + timedelta(hours=24)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

        exchange_resp = await ws_consumer.place_order(ws_payload)
        order.exchange_order_id = exchange_resp.get("order_id")
        order.status = OrderStatus.ACCEPTED
        await db.commit()
        await db.refresh(order)

        await kafka_producer.publish(
            "order.created",
            {
                "order_id": order.id,
                "user_id": user_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "type": order.order_type.value,
                "quantity": order.quantity,
                "price": float(order.price) if order.price else None,
                "status": order.status.value,
                "exchange_order_id": order.exchange_order_id,
            },
        )
        await kafka_producer.publish(
            "order.accepted",
            {"order_id": order.id, "user_id": user_id, "exchange_order_id": order.exchange_order_id},
        )

    except ExchangeWsError as e:
        order.status = OrderStatus.REJECTED
        order.reject_reason = str(e)
        await db.commit()
        await db.refresh(order)

        if reserved and reference_id:
            await wallet_client.release_funds(user_id, reference_id)

        await kafka_producer.publish(
            "order.rejected",
            {"order_id": order.id, "user_id": user_id, "reason": str(e)},
        )

    return order


async def get_fee_policy(db: AsyncSession) -> dict:
    platform_profit_total = await get_fee_revenue(db)
    return {
        "platform_fee_rate": float(await fee_policy.get_current_fee_rate(db)),
        "formula": platform_fees.PLATFORM_FEE_FORMULA,
        "rounding": platform_fees.PLATFORM_FEE_ROUNDING,
        "platform_profit_total": float(platform_profit_total),
    }


async def get_orders(db: AsyncSession, user_id: int) -> list[Order]:
    result = await db.execute(select(Order).where(Order.user_id == user_id))
    return list(result.scalars().all())


async def get_order(db: AsyncSession, user_id: int, order_id: int) -> Order:
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


async def cancel_order(db: AsyncSession, user_id: int, order_id: int) -> Order:
    order = await get_order(db, user_id, order_id)

    if order.status not in (OrderStatus.PENDING, OrderStatus.ACCEPTED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel order with status {order.status.value}",
        )

    if order.exchange_order_id:
        try:
            await exchange_client.cancel_order(order.exchange_order_id)
        except exchange_client.ExchangeError as e:
            raise HTTPException(status_code=502, detail=f"Exchange cancel failed: {e}")

    order.status = OrderStatus.CANCELLED
    await db.commit()
    await db.refresh(order)

    await kafka_producer.publish(
        "order.cancelled",
        {"order_id": order.id, "user_id": user_id, "exchange_order_id": order.exchange_order_id},
    )

    return order


async def get_fee_revenue(db: AsyncSession):
    result = await db.execute(
        select(func.coalesce(func.sum(Order.platform_fee), 0)).where(
            Order.status == OrderStatus.FILLED
        )
    )
    return result.scalar_one()


async def get_admin_metrics(db: AsyncSession) -> dict:
    total_orders = await db.scalar(select(func.count(Order.id))) or 0

    status_rows = await db.execute(
        select(Order.status, func.count(Order.id))
        .group_by(Order.status)
        .order_by(Order.status)
    )
    status_breakdown = [
        {"status": status.value if hasattr(status, "value") else str(status), "count": count}
        for status, count in status_rows.all()
    ]

    fill_value = func.coalesce(Order.filled_quantity, 0) * func.coalesce(Order.filled_price, 0)
    fill_filter = Order.status == OrderStatus.FILLED
    totals = await db.execute(
        select(
            func.coalesce(
                func.sum(case((fill_filter & (Order.side == OrderSide.BUY), Order.filled_quantity), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((fill_filter & (Order.side == OrderSide.SELL), Order.filled_quantity), else_=0)),
                0,
            ),
            func.coalesce(func.sum(case((fill_filter, fill_value), else_=0)), 0),
            func.coalesce(func.sum(case((fill_filter, Order.platform_fee), else_=0)), 0),
        )
    )
    bought_quantity, sold_quantity, traded_notional, fee_revenue = totals.one()

    top_rows = await db.execute(
        select(
            Order.symbol,
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.filled_quantity), 0).label("quantity"),
            func.coalesce(func.sum(fill_value), 0).label("traded_notional"),
            func.coalesce(func.sum(Order.platform_fee), 0).label("platform_fee"),
        )
        .where(fill_filter)
        .group_by(Order.symbol)
        .order_by(desc("traded_notional"))
        .limit(10)
    )
    top_symbols = [
        {
            "symbol": symbol,
            "orders": orders,
            "quantity": float(quantity or 0),
            "traded_notional": float(notional or 0),
            "platform_fee": float(platform_fee or 0),
        }
        for symbol, orders, quantity, notional, platform_fee in top_rows.all()
    ]

    return {
        "total_orders": total_orders,
        "status_breakdown": status_breakdown,
        "bought_quantity": float(bought_quantity or 0),
        "sold_quantity": float(sold_quantity or 0),
        "traded_notional": float(traded_notional or 0),
        "fee_revenue": float(fee_revenue or 0),
        "top_symbols": top_symbols,
    }
