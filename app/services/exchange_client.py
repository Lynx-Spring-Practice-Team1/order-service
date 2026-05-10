import httpx
from app.config import settings
from app.models import OrderSide, OrderType


class ExchangeError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


async def place_order(
    symbol: str,
    side: OrderSide,
    order_type: OrderType,
    quantity: int,
    price: float | None,
) -> dict:
    payload = {
        "symbol": symbol,
        "side": side.value,
        "type": order_type.value,
        "quantity": quantity,
    }
    if price is not None:
        payload["price"] = str(price)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.EXCHANGE_API_BASE_URL}/api/orders", json=payload
        )
        if resp.status_code not in (200, 201):
            raise ExchangeError(resp.text, resp.status_code)
        return resp.json()


async def cancel_order(exchange_order_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.delete(
            f"{settings.EXCHANGE_API_BASE_URL}/api/orders/{exchange_order_id}"
        )
        if resp.status_code not in (200, 204):
            raise ExchangeError(resp.text, resp.status_code)
        return resp.json() if resp.content else {}
