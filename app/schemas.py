from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.models import OrderSide, OrderType, OrderStatus


class OrderCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    side: OrderSide
    order_type: OrderType
    quantity: int = Field(..., gt=0)
    price: Optional[float] = Field(None, gt=0)
    market_price_estimate: Optional[float] = Field(None, gt=0)


class OrderResponse(BaseModel):
    id: int
    user_id: int
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: Optional[float]
    status: OrderStatus
    exchange_order_id: Optional[str]
    filled_quantity: int
    filled_price: Optional[float]
    exchange_fee: Optional[float]
    platform_fee: Optional[float]
    platform_fee_rate: Optional[float]
    total_fee: Optional[float]
    reject_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlatformFeePolicyResponse(BaseModel):
    platform_fee_rate: float
    formula: str
    rounding: str
    platform_profit_total: float
