# Order Service

Stock trading order execution and management microservice for the broker platform.

## Overview

Central order management system that accepts buy/sell orders, manages the full order lifecycle (PENDING → FILLED/REJECTED/CANCELLED), communicates with an external exchange via WebSocket, integrates with the wallet service for fund reservation, and publishes order events to Kafka. Also manages platform fee policy.

## Tech Stack

- **Python 3.12** + **FastAPI 0.111** + **uvicorn**
- **PostgreSQL** via SQLAlchemy 2.0 (asyncpg) + Alembic
- **WebSockets 12.0** — real-time exchange order updates
- **aiokafka 0.11** — async Kafka event producer
- **HTTPX 0.27** — async HTTP client (wallet/exchange REST)
- **python-jose** — JWT auth
- **Pydantic v2** — validation

## Project Structure

```
order-service/
├── app/
│   ├── main.py                         # FastAPI app, startup/lifespan
│   ├── config.py                       # Environment configuration
│   ├── auth.py                         # JWT and header-based auth
│   ├── database.py                     # SQLAlchemy async setup
│   ├── models.py                       # ORM: Order, BrokerFeePolicy
│   ├── schemas.py                      # Pydantic request/response models
│   ├── routers/
│   │   └── orders.py                   # All API endpoints
│   └── services/
│       ├── order_service.py            # Order creation and management
│       ├── fee_policy.py               # Fee rate management
│       ├── platform_fees.py            # Fee calculation (Decimal arithmetic)
│       ├── exchange_ws_consumer.py     # WebSocket listener for exchange
│       ├── exchange_client.py          # Exchange REST API client
│       ├── wallet_client.py            # Wallet service REST client
│       └── kafka_producer.py           # Kafka event publisher
├── tests/
│   ├── test_platform_fees.py
│   └── test_exchange_ws_fees.py
├── requirements.txt
└── Dockerfile
```

## API Endpoints

### User Endpoints (require `Authorization: Bearer <token>` or `X-User-Id` header)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/orders` | Create new order |
| `GET` | `/orders` | List user's orders |
| `GET` | `/orders/{order_id}` | Get order details |
| `DELETE` | `/orders/{order_id}` | Cancel pending/accepted order |
| `GET` | `/orders/fees` | Current platform fee policy |
| `GET` | `/orders/my-fees` | Total fees paid by current user |

### Internal/Admin Endpoints (require `X-Internal-Token` header)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/orders/internal/admin/metrics` | Platform-wide metrics (orders, volume, fees) |
| `GET` | `/orders/internal/admin/fee-policy` | Current fee policy |
| `POST` | `/orders/internal/admin/fee-policy` | Update fee rate (with audit log) |
| `GET` | `/orders/internal/admin/fee-policy/history` | Fee change history (paginated, max 100) |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | `{"status": "ok", "service": "order-service"}` |

## Order Lifecycle

```
PENDING → ACCEPTED → PARTIALLY_FILLED → FILLED
                   ↘ REJECTED
       ↘ CANCELLED
```

**Fund management (BUY orders):**
1. `reserve` — holds `trade_value + estimated_fee` in wallet
2. `settle` — deducts actual cost on fill; releases over-reservation
3. `release` — returns all funds on cancel/reject

**SELL orders:** `credit` — adds sale proceeds minus fees to wallet

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://broker:changeme@postgres:5432/orders_db` | PostgreSQL connection |
| `JWT_SECRET` | `change-me-in-production` | JWT signing secret |
| `INTERNAL_SERVICE_TOKEN` | `change-me-in-production` | Internal service token |
| `EXCHANGE_API_BASE_URL` | `http://host.docker.internal:8085` | Exchange REST API |
| `EXCHANGE_API_KEY` | — | Exchange API key |
| `EXCHANGE_API_SECRET` | — | Exchange API secret |
| `EXCHANGE_WS_URL` | `ws://host.docker.internal:8084/ws` | Exchange WebSocket |
| `WALLET_SERVICE_URL` | `http://wallet-service:8003` | Wallet service URL |
| `KAFKA_BOOTSTRAP_SERVERS` | `redpanda:9092` | Kafka broker |
| `PLATFORM_FEE_RATE` | `0.001` | Default fee rate (0.1%) |

## Getting Started

### Local Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

### Docker

```bash
docker build -t order-service .
docker run -p 8002:8002 --env-file .env order-service
```

### Tests

```bash
python -m pytest tests/
```

## Kafka Events Published

| Topic | Trigger |
|-------|---------|
| `order.created` | New order submitted |
| `order.accepted` | Exchange acknowledged |
| `order.rejected` | Exchange or service rejected |
| `order.filled` | Order fully executed |
| `order.cancelled` | Order cancelled |

## Deployment

GitHub Actions CI/CD pushes to GHCR on push to `main`:
```
ghcr.io/lynx-spring-practice-team1/order-service:latest
```
