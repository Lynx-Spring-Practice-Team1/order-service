import asyncio
import json
import logging
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Order, OrderStatus
from app.services import kafka_producer, platform_fees, wallet_client

logger = logging.getLogger(__name__)
RECONNECT_DELAY = 5

_PROCESSABLE_STATUSES = {"FILLED", "PARTIALLY_FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
_STATUS_MAP = {
    "FILLED": OrderStatus.FILLED,
    "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "EXPIRED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
}


class ExchangeWsError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ExchangeWsConsumer:
    def __init__(self):
        self._ws = None
        self._pending_order: asyncio.Future | None = None
        self._order_lock = asyncio.Lock()

    async def place_order(self, payload: dict) -> dict:
        if self._ws is None:
            raise ExchangeWsError("WS_DISCONNECTED", "WebSocket not connected")

        async with self._order_lock:
            loop = asyncio.get_event_loop()
            self._pending_order = loop.create_future()
            try:
                await self._ws.send(json.dumps({
                    "type": "PLACE_ORDER",
                    "payload": payload,
                }))
                return await asyncio.wait_for(
                    asyncio.shield(self._pending_order), timeout=10.0
                )
            except asyncio.TimeoutError:
                raise ExchangeWsError("TIMEOUT", "No ACK from exchange within 10 s")
            finally:
                self._pending_order = None

    async def run(self):
        import websockets
        url = (
            f"{settings.EXCHANGE_WS_URL}"
            f"?api_key={settings.EXCHANGE_API_KEY}"
            f"&api_secret={settings.EXCHANGE_API_SECRET}"
        )
        while True:
            try:
                async with websockets.connect(url) as ws:
                    self._ws = ws
                    await ws.send(json.dumps({
                        "type": "SUBSCRIBE",
                        "payload": {"channel": "ORDER_UPDATES"},
                    }))
                    logger.info("Exchange WS connected, subscribed to ORDER_UPDATES")
                    async for raw in ws:
                        try:
                            await self._dispatch(json.loads(raw))
                        except Exception as e:
                            logger.error("WS message error: %s", e)
            except Exception as e:
                logger.warning(
                    "Exchange WS disconnected: %s — reconnecting in %ds", e, RECONNECT_DELAY
                )
            finally:
                self._ws = None
                if self._pending_order and not self._pending_order.done():
                    self._pending_order.set_exception(
                        ExchangeWsError("WS_DISCONNECTED", "WebSocket disconnected mid-order")
                    )
            await asyncio.sleep(RECONNECT_DELAY)

    async def _dispatch(self, msg: dict):
        msg_type = msg.get("type")
        payload = msg.get("payload", {})
        if msg_type == "ORDER_ACK":
            self._resolve_pending(payload)
        elif msg_type == "ORDER_REJECTED":
            self._reject_pending(payload)
        elif msg_type == "ORDER_UPDATE":
            await _handle_order_update(payload)

    def _resolve_pending(self, payload: dict):
        if self._pending_order and not self._pending_order.done():
            self._pending_order.set_result(payload)

    def _reject_pending(self, payload: dict):
        if self._pending_order and not self._pending_order.done():
            self._pending_order.set_exception(
                ExchangeWsError(
                    payload.get("code", "ORDER_REJECTED"),
                    payload.get("message", "Order rejected by exchange"),
                )
            )


# Module-level singleton accessed by order_service
consumer = ExchangeWsConsumer()


# Kept so main.py requires no changes
async def run():
    await consumer.run()


async def _handle_order_update(payload: dict):
    exchange_order_id = payload.get("order_id")
    status = payload.get("status")
    if not exchange_order_id or status not in _PROCESSABLE_STATUSES:
        return

    filled_quantity = payload.get("filled_quantity", 0) or 0
    average_fill_price = payload.get("average_fill_price", 0.0) or 0.0
    exchange_fee = platform_fees.money(payload.get("exchange_fee", 0.0) or 0.0)
    market_time = payload.get("market_time", datetime.now(timezone.utc).isoformat())
    platform_fee_rate = platform_fees.get_platform_fee_rate()
    platform_fee = platform_fees.calculate_platform_fee(
        filled_quantity,
        average_fill_price,
        platform_fee_rate,
    ) if status == "FILLED" else platform_fees.money(0)
    total_fee = platform_fees.calculate_total_fee(exchange_fee, platform_fee)
    trade_value = platform_fees.calculate_trade_value(filled_quantity, average_fill_price)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Order).where(Order.exchange_order_id == exchange_order_id)
        )
        order = result.scalar_one_or_none()
        if order is None:
            logger.warning("Received update for unknown exchange_order_id=%s", exchange_order_id)
            return
        if status == "FILLED" and order.status == OrderStatus.FILLED and order.platform_fee is not None:
            logger.info("Ignoring duplicate FILLED update for exchange_order_id=%s", exchange_order_id)
            return

        mapped = _STATUS_MAP.get(status)
        if mapped is None:
            return
        order.status = mapped
        order.filled_quantity = filled_quantity
        if average_fill_price:
            order.filled_price = average_fill_price
        order.exchange_fee = exchange_fee
        if status == "FILLED":
            order.platform_fee = platform_fee
            order.platform_fee_rate = platform_fee_rate

        await db.commit()
        await db.refresh(order)

        order_id = order.id
        user_id = order.user_id
        symbol = order.symbol
        side = order.side.value
        wallet_reference_id = order.wallet_reference_id

    if status == "FILLED":
        await kafka_producer.publish("order.filled", {
            "event_id": str(uuid4()),
            "order_id": str(order_id),
            "user_id": str(user_id),
            "symbol": symbol,
            "side": side,
            "quantity": filled_quantity,
            "price": average_fill_price,
            "filled_at": market_time,
            "exchange_fee": float(exchange_fee),
            "platform_fee": float(platform_fee),
            "platform_fee_rate": float(platform_fee_rate),
            "total_fee": float(total_fee),
        })
        if side == "BUY" and wallet_reference_id:
            try:
                await wallet_client.settle_trade(
                    user_id,
                    wallet_reference_id,
                    float(trade_value + total_fee),
                )
                platform_fees.record_platform_profit(platform_fee)
            except Exception as e:
                logger.error("Wallet settlement failed for order %s: %s", order_id, e)
        elif side == "SELL":
            proceeds = max(platform_fees.money(0), trade_value - total_fee)
            try:
                await wallet_client.credit_funds(user_id, float(proceeds))
                platform_fees.record_platform_profit(platform_fee)
            except Exception as e:
                logger.error("Wallet credit failed for order %s: %s", order_id, e)

    elif status in ("CANCELLED", "EXPIRED", "REJECTED"):
        topic = "order.rejected" if status == "REJECTED" else "order.cancelled"
        await kafka_producer.publish(topic, {
            "order_id": order_id,
            "user_id": user_id,
            "exchange_order_id": exchange_order_id,
            "reason": status,
        })
        if side == "BUY" and wallet_reference_id:
            try:
                await wallet_client.release_funds(user_id, wallet_reference_id)
            except Exception as e:
                logger.error("Wallet release failed for order %s: %s", order_id, e)
