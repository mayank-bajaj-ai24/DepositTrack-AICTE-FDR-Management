"""Application settings, read from environment variables (prefix DT_)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DT_", env_file=".env", extra="ignore")

    app_name: str = "DepositTrack API"
    environment: str = "development"

    database_url: str = (
        "postgresql+psycopg://depositrack:dev-only-change-me@localhost:5432/depositrack"
    )

    keycloak_issuer: str = "http://localhost:8080/realms/depositrack"
    # Clients whose tokens the API accepts (checked against the `azp` claim).
    allowed_clients: list[str] = ["depositrack-web", "depositrack-dev-cli"]

    s3_endpoint: str = "http://localhost:8333"
    s3_bucket: str = "depositrack-documents"

    policy_file: str = "config/policy.example.yaml"

    @property
    def jwks_url(self) -> str:
        return f"{self.keycloak_issuer}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
