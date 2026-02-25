from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    open_api_service_key: str = ""
    open_api_base_url: str = ""
    database_url: str = "sqlite:///./market_share.db"
    api_timeout_seconds: int = 20

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
