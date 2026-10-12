"""Server settings, read from environment variables and `.env`."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    auth_mode: Literal["none", "api_key", "oauth"] = "none"
    api_key: str = ""

    database_url: str = "postgresql+asyncpg://fitgen:fitgen@localhost:5434/fitgen"

    llm_provider: Literal["groq", "bedrock"] = "groq"
    groq_api_key: str = ""

    queue_backend: Literal["local", "sqs"] = "local"

    aws_region: str = "us-east-1"
    bedrock_model_id: str = "amazon.nova-lite-v1:0"
    sqs_queue_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
