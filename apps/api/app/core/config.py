"""Application settings, read from environment variables (prefix DT_) or apps/api/.env."""

from functools import lru_cache
from typing import Literal

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
    cors_origins: list[str] = ["http://localhost:3000"]

    # Document storage (M2). Files are encrypted by the app before they reach the store.
    storage_backend: Literal["s3", "local"] = "s3"
    storage_local_dir: str = "var/storage"
    s3_endpoint: str = "http://localhost:8333"
    s3_bucket: str = "depositrack-documents"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    # Fernet key (urlsafe base64, 32 bytes). Required to store or read documents.
    storage_encryption_key: str = ""
    max_upload_mb: int = 10

    # Policy file: config/policy.example.yaml (real, all unconfirmed) or a demo file.
    policy_file: str = "config/policy.example.yaml"

    # Bank verification channel (M5, N3). In the prototype this is services/mock-bank.
    bank_api_url: str = "http://127.0.0.1:8090"
    bank_api_token: str = ""
    # Pinned bank public keys: fetched once by an admin, then trusted (never refetched silently).
    bank_keys_file: str = "var/bank-keys/pinned.json"
    models_dir: str = "../../models"

    # immudb anchoring (N4); anchoring is skipped when disabled.
    immudb_enabled: bool = False
    immudb_host: str = "localhost"
    immudb_port: int = 3322
    immudb_user: str = "immudb"
    immudb_password: str = ""

    @property
    def jwks_url(self) -> str:
        return f"{self.keycloak_issuer}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
