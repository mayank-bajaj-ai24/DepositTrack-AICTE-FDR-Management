from fastapi import FastAPI

from app.core.config import get_settings
from app.core.policy import load_policy, unconfirmed_keys
from app.modules.auth.router import router as auth_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.include_router(auth_router)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "environment": settings.environment}

    @app.get("/api/v1/policy/status", tags=["system"])
    def policy_status() -> dict:
        """Which AICTE policy values are still unconfirmed (plan §14)."""
        policy = load_policy(settings.policy_file)
        return {
            "policy_version": policy.get("policy_version"),
            "unconfirmed": unconfirmed_keys(policy),
        }

    return app


app = create_app()
