from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, audit, dashboard, instruments, release
from app.core.config import get_settings
from app.core.policy import load_policy, unconfirmed_keys
from app.modules.auth.router import router as auth_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Content-SHA256", "Content-Disposition"],
    )
    app.include_router(auth_router)
    app.include_router(instruments.router)
    app.include_router(release.router)
    app.include_router(dashboard.router)
    app.include_router(audit.router)
    app.include_router(admin.router)

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
