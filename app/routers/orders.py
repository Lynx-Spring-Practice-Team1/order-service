from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.schemas import (
    FeePolicyHistoryItem,
    OrderAdminMetrics,
    OrderCreate,
    OrderResponse,
    PlatformFeePolicyResponse,
    PlatformFeePolicyUpdate,
)
from app.services import fee_policy, order_service

router = APIRouter(prefix="/orders", tags=["orders"])


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    if x_internal_token != settings.INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")


@router.post("/", response_model=OrderResponse, status_code=201)
async def create_order(
    body: OrderCreate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await order_service.create_order(db, user_id, body)


@router.get("/", response_model=list[OrderResponse])
async def list_orders(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await order_service.get_orders(db, user_id)


@router.get("/fees", response_model=PlatformFeePolicyResponse)
async def get_fee_policy(db: AsyncSession = Depends(get_db)):
    return await order_service.get_fee_policy(db)


@router.get("/internal/admin/metrics", response_model=OrderAdminMetrics)
async def get_admin_metrics(
    _: None = Depends(require_internal_token),
    db: AsyncSession = Depends(get_db),
):
    return await order_service.get_admin_metrics(db)


@router.get("/internal/admin/fee-policy", response_model=PlatformFeePolicyResponse)
async def get_admin_fee_policy(
    _: None = Depends(require_internal_token),
    db: AsyncSession = Depends(get_db),
):
    return await order_service.get_fee_policy(db)


@router.post("/internal/admin/fee-policy", response_model=FeePolicyHistoryItem)
async def update_admin_fee_policy(
    body: PlatformFeePolicyUpdate,
    _: None = Depends(require_internal_token),
    x_admin_user: str | None = Header(default="admin", alias="X-Admin-User"),
    db: AsyncSession = Depends(get_db),
):
    return await fee_policy.set_current_fee_rate(
        db,
        body.platform_fee_rate,
        changed_by=x_admin_user or "admin",
        reason=body.reason,
    )


@router.get("/internal/admin/fee-policy/history", response_model=list[FeePolicyHistoryItem])
async def get_admin_fee_history(
    _: None = Depends(require_internal_token),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
):
    return await fee_policy.get_fee_history(db, limit)


@router.get("/my-fees", response_model=dict)
async def get_my_fees(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func, select
    from app.models import Order, OrderStatus
    base = select(Order).where(Order.user_id == user_id, Order.status == OrderStatus.FILLED)
    r1 = await db.execute(select(func.coalesce(func.sum(Order.platform_fee), 0)).where(
        Order.user_id == user_id, Order.status == OrderStatus.FILLED,
    ))
    r2 = await db.execute(select(func.coalesce(func.sum(Order.exchange_fee), 0)).where(
        Order.user_id == user_id, Order.status == OrderStatus.FILLED,
    ))
    return {
        "total_fees_paid": float(r1.scalar() or 0),
        "total_exchange_fees": float(r2.scalar() or 0),
    }


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await order_service.get_order(db, user_id, order_id)


@router.delete("/{order_id}", response_model=OrderResponse)
async def cancel_order(
    order_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await order_service.cancel_order(db, user_id, order_id)
