import enum
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, Numeric, Enum, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING
    )
    exchange_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    wallet_reference_id: Mapped[str] = mapped_column(String(200), nullable=True)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filled_price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=True)
    exchange_fee: Mapped[float] = mapped_column(Numeric(18, 6), nullable=True)
    platform_fee: Mapped[float] = mapped_column(Numeric(18, 6), nullable=True)
    platform_fee_rate: Mapped[float] = mapped_column(Numeric(18, 6), nullable=True)
    reject_reason: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def total_fee(self) -> Decimal | None:
        if self.exchange_fee is None and self.platform_fee is None:
            return None
        exchange_fee = Decimal(str(self.exchange_fee or 0))
        platform_fee = Decimal(str(self.platform_fee or 0))
        return exchange_fee + platform_fee
