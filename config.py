import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_env_file() -> str:
    """Determine which .env file to load based on INSTANCE or NODE_ENV."""
    env = os.getenv("INSTANCE", os.getenv("NODE_ENV", "local")).lower()
    if "pipl" in env:
        target = os.path.join(BASE_DIR, ".env.pipl")
    elif "ndcs" in env:
        target = os.path.join(BASE_DIR, ".env.ndcs")
    else:
        target = os.path.join(BASE_DIR, ".env")
        if not os.path.exists(target):
            target = os.path.join(BASE_DIR, ".env.example")
    return target


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server settings
    PORT: int = 4006
    HOST: str = "0.0.0.0"
    INSTANCE_NAME: str = "PIPL"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"

    # Google Gemini AI
    GEMINI_API_KEY: str = ""
    GEMINI_FLASH_MODEL: str = "gemini-3.5-flash"
    GEMINI_PRO_MODEL: str = "gemini-2.5-pro"

    # AWS Credentials
    AWS_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    S3_QUOTATION_BUCKET: Optional[str] = None
    S3_QUAOAR_BUCKET: Optional[str] = None

    # Database URIs
    ERP_MONGO_URI: str = "mongodb://localhost:27017/erp?readPreference=secondaryPreferred"
    SC_MONGO_URI: Optional[str] = "mongodb://localhost:27017/sc?readPreference=secondaryPreferred"
    MES_MONGO_URI: str = "mongodb://localhost:27017/mes?readPreference=secondaryPreferred"
    AI_CHAT_MONGO_URI: str = "mongodb://localhost:27017/ai_service"

    # Quaoar CAD Microservice
    QUAOAR_URL: str = "http://localhost:4004"


settings = Settings()
