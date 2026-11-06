from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração da aplicação, lida de variáveis de ambiente (ou de um arquivo .env)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    trello_api_key: SecretStr | None = None
    trello_token: SecretStr | None = None
    trello_base_url: str = "https://api.trello.com/1"
    trello_timeout_seconds: float = Field(default=10.0, gt=0)
    trello_max_retries: int = Field(default=3, ge=0, le=10)
    trello_backoff_seconds: float = Field(default=1.0, ge=0)

    max_upload_bytes: int = Field(default=1_048_576, gt=0)
    max_files_per_request: int = Field(default=20, gt=0)

    log_level: str = "INFO"

    @property
    def trello_configured(self) -> bool:
        return bool(
            self.trello_api_key
            and self.trello_api_key.get_secret_value().strip()
            and self.trello_token
            and self.trello_token.get_secret_value().strip()
        )

    def secret_values(self) -> list[str]:
        """Valores que nunca devem aparecer em logs."""
        return [
            secret.get_secret_value()
            for secret in (self.trello_api_key, self.trello_token)
            if secret and secret.get_secret_value()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
