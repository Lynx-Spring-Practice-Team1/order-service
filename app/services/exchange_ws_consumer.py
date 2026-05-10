import asyncio
import json
import logging
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Order, OrderStatus
from app.services import kafka_producer, wallet_client

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 5


async def _handle_order_update(payload: dict):
    exchange_order_id = payload.get("order_id")
    status = payload.get("status")

    if not exchange_order_id or status != "FILLED":
        return

    filled_quantity = payload.get("filled_quantity", 0)
    average_fill_price = payload.get("average_fill_price", 0.0)
    market_time = payload.get("market_time", datetime.now(timezone.utc).isoformat())

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Order).where(Order.exchange_order_id == exchange_order_id)
        )
        order = result.scalar_one_or_none()
        if order is None:
            logger.warning("Received fill for unknown exchange_order_id=%s", exchange_order_id)
            return

        order.status = OrderStatus.FILLED
        order.filled_quantity = filled_quantity
        order.filled_price = average_fill_price
        await db.commit()
        await db.refresh(order)

        order_id = order.id
        user_id = order.user_id
        symbol = order.symbol
        side = order.side.value
        wallet_reference_id = order.wallet_reference_id

    await kafka_producer.publish(
        "order.filled",
        {
            "event_id": str(uuid4()),
            "order_id": str(order_id),
            "user_id": str(user_id),
            "symbol": symbol,
            "side": side,
            "quantity": filled_quantity,
            "price": average_fill_price,
            "filled_at": market_time,
        },
    )

    if side == "BUY" and wallet_reference_id:
        actual_cost = filled_quantity * average_fill_price
        try:
            await wallet_client.settle_trade(user_id, wallet_reference_id, actual_cost)
        except Exception as e:
            logger.error("Wallet settlement failed for order %s: %s", order_id, e)


async def run():
    import websockets

    url = f"{settings.EXCHANGE_WS_URL}?api_key={settings.EXCHANGE_API_KEY}&api_secret={settings.EXCHANGE_API_SECRET}"

    while True:
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({
                    "type": "SUBSCRIBE",
                    "payload": {"channels": ["ORDER_UPDATES"]},
                }))
                logger.info("Exchange WS connected, subscribed to ORDER_UPDATES")

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        if msg.get("type") == "ORDER_UPDATE":
                            await _handle_order_update(msg.get("payload", {}))
                    except Exception as e:
                        logger.error("WS message error: %s", e)

        except Exception as e:
            logger.warning("Exchange WS disconnected: %s — reconnecting in %ds", e, RECONNECT_DELAY)
            await asyncio.sleep(RECONNECT_DELAY)
