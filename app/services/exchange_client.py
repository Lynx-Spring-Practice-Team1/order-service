import httpx
from datetime import datetime, timezone, timedelta
from app.config import settings
from app.models import OrderSide, OrderType


class ExchangeError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


def _auth_headers() -> dict:
    return {
        "API-KEY": settings.EXCHANGE_API_KEY,
        "API-SECRET": settings.EXCHANGE_API_SECRET,
    }


async def place_order(
    symbol: str,
    side: OrderSide,
    order_type: OrderType,
    quantity: int,
    price: float | None,
    platform_user_id: int,
) -> dict:
    payload = {
        "platform_user_id": str(platform_user_id),
        "instrument_type": "STOCK",
        "instrument_id": symbol,
        "order_type": order_type.value,
        "side": side.value,
        "quantity": quantity,
    }
    if order_type == OrderType.LIMIT:
        payload["limit_price"] = float(price)
        payload["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(hours=24)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.EXCHANGE_API_BASE_URL}/api/v1/orders",
            json=payload,
            headers=_auth_headers(),
        )
        if resp.status_code not in (200, 201):
            raise ExchangeError(resp.text, resp.status_code)
        return resp.json()


async def cancel_order(exchange_order_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.delete(
            f"{settings.EXCHANGE_API_BASE_URL}/api/v1/orders/{exchange_order_id}",
            headers=_auth_headers(),
        )
        if resp.status_code not in (200, 204):
            raise ExchangeError(resp.text, resp.status_code)
        return resp.json() if resp.content else {}
