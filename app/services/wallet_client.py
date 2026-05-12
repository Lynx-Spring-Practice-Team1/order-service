import httpx
from app.config import settings


class WalletError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


async def reserve_funds(user_id: int, amount: float, reference_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.WALLET_SERVICE_URL}/wallet/reserve",
            json={"user_id": user_id, "amount": amount, "reference_id": reference_id},
        )
        if resp.status_code != 200:
            raise WalletError(resp.json().get("detail", "Reserve failed"), resp.status_code)
        return resp.json()


async def release_funds(user_id: int, reference_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.WALLET_SERVICE_URL}/wallet/release",
            json={"user_id": user_id, "reference_id": reference_id},
        )
        if resp.status_code != 200:
            raise WalletError(resp.json().get("detail", "Release failed"), resp.status_code)
        return resp.json()


async def settle_trade(user_id: int, reference_id: str, actual_amount: float) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.WALLET_SERVICE_URL}/wallet/settle",
            json={"user_id": user_id, "reference_id": reference_id, "actual_amount": actual_amount},
        )
        if resp.status_code != 200:
            raise WalletError(resp.json().get("detail", "Settle failed"), resp.status_code)
        return resp.json()


async def credit_funds(user_id: int, amount: float) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.WALLET_SERVICE_URL}/wallet/credit",
            json={"user_id": user_id, "amount": amount},
        )
        if resp.status_code != 200:
            raise WalletError(resp.json().get("detail", "Credit failed"), resp.status_code)
        return resp.json()
