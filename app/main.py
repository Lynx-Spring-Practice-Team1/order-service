import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import orders
from app.services.kafka_producer import stop_producer
from app.services import exchange_ws_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    ws_task = asyncio.create_task(exchange_ws_consumer.run())
    yield
    ws_task.cancel()
    await stop_producer()


app = FastAPI(
    title="Order Service",
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "Order execution service for the broker platform.\n\n"
        "Platform fee policy: stock fills are charged a configurable platform fee in "
        "addition to the exchange fee. The default platform fee rate is 0.1% of executed "
        "trade value. Formula: platform_fee = execution_price * quantity * "
        "platform_fee_rate, rounded half up to 2 decimal places. The current fee policy "
        "is exposed at GET /orders/fees."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "order-service"}
