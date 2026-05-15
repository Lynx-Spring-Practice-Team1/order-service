from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.schemas import OrderCreate, OrderResponse, PlatformFeePolicyResponse
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"])


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
async def get_fee_policy():
    return order_service.get_fee_policy()


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
