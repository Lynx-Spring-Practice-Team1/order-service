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


app = FastAPI(title="Order Service", version="1.0.0", lifespan=lifespan)

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
