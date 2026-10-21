"""Shared FastAPI dependencies: policy, storage, extraction and the bank channel."""

from fastapi import Depends, HTTPException, status

from app.core.access import Scope
from app.core.config import Settings, get_settings
from app.core.configfiles import load_config
from app.core.policy import Policy, get_policy
from app.modules.audit.service import Actor
from app.modules.bank.client import BankChannelError, BankClient
from app.modules.extraction.ocr import UnsupportedDocumentError, load_image
from app.modules.extraction.service import ExtractionResult, extract
from app.modules.storage.store import DocumentStore, StorageError, build_store


def policy_dep(settings: Settings = Depends(get_settings)) -> Policy:
    return get_policy(settings.policy_file)


_stores: dict[tuple, DocumentStore] = {}


def store_dep(settings: Settings = Depends(get_settings)) -> DocumentStore:
    key = (
        settings.storage_backend,
        settings.storage_local_dir,
        settings.s3_endpoint,
        settings.s3_bucket,
        settings.storage_encryption_key,
    )
    try:
        if key not in _stores:
            _stores[key] = build_store(settings)
        return _stores[key]
    except StorageError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def extractor_dep(settings: Settings = Depends(get_settings)):
    def run(data: bytes, content_type: str | None) -> ExtractionResult | None:
        try:
            image = load_image(data, content_type)
        except UnsupportedDocumentError:
            return None
        return extract(image, load_config("extraction.yaml"), settings.models_dir)

    return run


def bank_dep(settings: Settings = Depends(get_settings)) -> BankClient | None:
    try:
        return BankClient(settings)
    except BankChannelError:
        return None


def actor_of(scope: Scope) -> Actor:
    return Actor(username=scope.principal.username, role=scope.role)
