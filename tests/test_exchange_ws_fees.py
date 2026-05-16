import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.models import Order, OrderSide, OrderStatus, OrderType
from app.services import platform_fees
from app.services.exchange_ws_consumer import _handle_order_update


class FakeScalarResult:
    def __init__(self, order: Order) -> None:
        self.order = order

    def scalar_one_or_none(self) -> Order:
        return self.order


class FakeSession:
    def __init__(self, order: Order) -> None:
        self.order = order
        self.commits = 0
        self.refreshes = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def execute(self, _):
        return FakeScalarResult(self.order)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, _) -> None:
        self.refreshes += 1


def make_order(side: OrderSide, wallet_reference_id: str | None = None) -> Order:
    return Order(
        id=1,
        user_id=7,
        symbol="ARKA",
        side=side,
        order_type=OrderType.MARKET,
        quantity=50,
        price=None,
        status=OrderStatus.ACCEPTED,
        exchange_order_id="exchange-1",
        wallet_reference_id=wallet_reference_id,
        filled_quantity=0,
        platform_fee_rate=Decimal("0.001"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class ExchangeWsFeeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        platform_fees.reset_platform_profit_total()

    async def test_filled_buy_stores_fees_settles_total_cost_and_publishes_fee_payload(self) -> None:
        order = make_order(OrderSide.BUY, wallet_reference_id="reserve-1")
        session = FakeSession(order)
        payload = {
            "order_id": "exchange-1",
            "status": "FILLED",
            "filled_quantity": 50,
            "average_fill_price": 130.10,
            "exchange_fee": 6.51,
            "market_time": "2026-05-15T10:00:00Z",
        }

        with (
            patch("app.services.exchange_ws_consumer.AsyncSessionLocal", return_value=session),
            patch("app.services.exchange_ws_consumer.kafka_producer.publish", new=AsyncMock()) as publish,
            patch("app.services.exchange_ws_consumer.wallet_client.settle_trade", new=AsyncMock()) as settle,
        ):
            await _handle_order_update(payload)

        self.assertEqual(order.exchange_fee, Decimal("6.51"))
        self.assertEqual(order.platform_fee, Decimal("6.51"))
        self.assertEqual(order.platform_fee_rate, Decimal("0.001"))
        settle.assert_awaited_once_with(7, "reserve-1", 6518.02)
        publish.assert_awaited_once()
        published_payload = publish.await_args.args[1]
        self.assertEqual(published_payload["exchange_fee"], 6.51)
        self.assertEqual(published_payload["platform_fee"], 6.51)
        self.assertEqual(published_payload["total_fee"], 13.02)
        self.assertEqual(platform_fees.get_platform_profit_total(), Decimal("0.00"))

    async def test_filled_sell_credits_net_proceeds_and_records_profit(self) -> None:
        order = make_order(OrderSide.SELL)
        session = FakeSession(order)
        payload = {
            "order_id": "exchange-1",
            "status": "FILLED",
            "filled_quantity": 50,
            "average_fill_price": 130.10,
            "exchange_fee": 6.51,
        }

        with (
            patch("app.services.exchange_ws_consumer.AsyncSessionLocal", return_value=session),
            patch("app.services.exchange_ws_consumer.kafka_producer.publish", new=AsyncMock()),
            patch("app.services.exchange_ws_consumer.wallet_client.credit_funds", new=AsyncMock()) as credit,
        ):
            await _handle_order_update(payload)

        credit.assert_awaited_once_with(7, 6491.98)
        self.assertEqual(order.platform_fee, Decimal("6.51"))
        self.assertEqual(platform_fees.get_platform_profit_total(), Decimal("0.00"))

    async def test_filled_update_uses_order_locked_platform_fee_rate(self) -> None:
        order = make_order(OrderSide.BUY, wallet_reference_id="reserve-1")
        order.platform_fee_rate = Decimal("0.002")
        session = FakeSession(order)
        payload = {
            "order_id": "exchange-1",
            "status": "FILLED",
            "filled_quantity": 50,
            "average_fill_price": 130.10,
            "exchange_fee": 6.51,
        }

        with (
            patch("app.services.exchange_ws_consumer.AsyncSessionLocal", return_value=session),
            patch("app.services.exchange_ws_consumer.kafka_producer.publish", new=AsyncMock()) as publish,
            patch("app.services.exchange_ws_consumer.wallet_client.settle_trade", new=AsyncMock()) as settle,
        ):
            await _handle_order_update(payload)

        self.assertEqual(order.platform_fee, Decimal("13.01"))
        self.assertEqual(order.platform_fee_rate, Decimal("0.002"))
        settle.assert_awaited_once_with(7, "reserve-1", 6524.52)
        published_payload = publish.await_args.args[1]
        self.assertEqual(published_payload["platform_fee_rate"], 0.002)
        self.assertEqual(published_payload["platform_fee"], 13.01)

    async def test_duplicate_filled_update_does_not_charge_or_publish_again(self) -> None:
        order = make_order(OrderSide.BUY, wallet_reference_id="reserve-1")
        order.status = OrderStatus.FILLED
        order.platform_fee = Decimal("6.51")
        session = FakeSession(order)
        payload = {
            "order_id": "exchange-1",
            "status": "FILLED",
            "filled_quantity": 50,
            "average_fill_price": 130.10,
            "exchange_fee": 6.51,
        }

        with (
            patch("app.services.exchange_ws_consumer.AsyncSessionLocal", return_value=session),
            patch("app.services.exchange_ws_consumer.kafka_producer.publish", new=AsyncMock()) as publish,
            patch("app.services.exchange_ws_consumer.wallet_client.settle_trade", new=AsyncMock()) as settle,
        ):
            await _handle_order_update(payload)

        publish.assert_not_awaited()
        settle.assert_not_awaited()
        self.assertEqual(platform_fees.get_platform_profit_total(), Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
