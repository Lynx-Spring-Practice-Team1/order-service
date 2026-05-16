from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BrokerFeePolicy
from app.services import platform_fees


def normalize_fee_rate(value) -> Decimal:
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid platform fee rate")
    if rate < 0:
        raise HTTPException(status_code=422, detail="Platform fee rate cannot be negative")
    return rate


async def get_current_fee_rate(db: AsyncSession) -> Decimal:
    result = await db.execute(
        select(BrokerFeePolicy)
        .order_by(desc(BrokerFeePolicy.created_at), desc(BrokerFeePolicy.id))
        .limit(1)
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        return platform_fees.get_platform_fee_rate()
    return normalize_fee_rate(policy.platform_fee_rate)


async def set_current_fee_rate(
    db: AsyncSession,
    rate,
    changed_by: str = "admin",
    reason: str | None = None,
) -> BrokerFeePolicy:
    policy = BrokerFeePolicy(
        platform_fee_rate=normalize_fee_rate(rate),
        changed_by=changed_by,
        reason=reason,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


async def get_fee_history(db: AsyncSession, limit: int = 25) -> list[BrokerFeePolicy]:
    result = await db.execute(
        select(BrokerFeePolicy)
        .order_by(desc(BrokerFeePolicy.created_at), desc(BrokerFeePolicy.id))
        .limit(limit)
    )
    return list(result.scalars().all())
