from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://order_user:order_pass@localhost:5433/order_db"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    EXCHANGE_API_BASE_URL: str = "http://localhost:8090"
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    WALLET_SERVICE_URL: str = "http://localhost:8002"

    class Config:
        env_file = ".env"


settings = Settings()
