from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    DATABASE_URL: str = "postgresql+asyncpg://broker:changeme@postgres:5432/orders_db"
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="redpanda:9092",
        validation_alias=AliasChoices("KAFKA_BOOTSTRAP_SERVERS", "KAFKA_BROKERS"),
    )
    EXCHANGE_API_BASE_URL: str = Field(
        default="http://host.docker.internal:8085",
        validation_alias=AliasChoices("EXCHANGE_API_BASE_URL", "EXCHANGE_REST_API_URL"),
    )
    EXCHANGE_API_KEY: str = "test-key"
    EXCHANGE_API_SECRET: str = "test-secret"
    EXCHANGE_WS_URL: str = "ws://host.docker.internal:8084/ws"
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    WALLET_SERVICE_URL: str = "http://wallet-service:8003"
    PLATFORM_FEE_RATE: str = Field(default="0.001", validation_alias="PLATFORM_FEE_RATE")


settings = Settings()
