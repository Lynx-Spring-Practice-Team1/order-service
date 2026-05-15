from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_order_fee_columns)


def _ensure_order_fee_columns(conn) -> None:
    inspector = inspect(conn)
    if "orders" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("orders")}
    fee_columns = {
        "platform_fee": "ALTER TABLE orders ADD COLUMN platform_fee NUMERIC(18, 6)",
        "platform_fee_rate": "ALTER TABLE orders ADD COLUMN platform_fee_rate NUMERIC(18, 6)",
    }

    for column_name, statement in fee_columns.items():
        if column_name not in existing_columns:
            conn.execute(text(statement))
