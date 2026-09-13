from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    vault_path: Path = Path("sample_vault")
    vault_name: str = "个人知识库示例"
    index_path: Path = Path("data/index.json")

    chat_base_url: str = "https://api.deepseek.com"
    chat_api_key: SecretStr | None = None
    chat_model: str = "deepseek-chat"

    embedding_base_url: str = "http://127.0.0.1:11434/v1"
    embedding_api_key: SecretStr | None = None
    embedding_model: str = "bge-m3"


@lru_cache
def get_settings() -> Settings:
    return Settings()
