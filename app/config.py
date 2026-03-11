from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://localhost:5432/impactoutreach"
    MAILGUN_API_KEY: str = ""
    MAILGUN_DOMAIN: str = "mail.impactoutreach.co"
    OPENAI_API_KEY: str = ""
    APP_SECRET_KEY: str = "change-me-in-production"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "changeme"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
