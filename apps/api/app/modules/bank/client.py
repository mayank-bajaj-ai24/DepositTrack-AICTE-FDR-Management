"""HTTP adapter for the bank verification channel (M5). In the prototype: services/mock-bank."""

import httpx

from app.core.config import Settings


class BankChannelError(RuntimeError):
    pass


class BankClient:
    def __init__(self, settings: Settings):
        if not settings.bank_api_token:
            raise BankChannelError("DT_BANK_API_TOKEN is not set")
        self.base = settings.bank_api_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.bank_api_token}"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        try:
            response = httpx.get(
                f"{self.base}{path}", params=params, headers=self.headers, timeout=10
            )
        except httpx.HTTPError as exc:
            raise BankChannelError(f"bank channel unreachable: {exc}") from exc
        if response.status_code == 404:
            raise BankChannelError("the bank has no record of this FDR")
        if response.status_code != 200:
            raise BankChannelError(f"bank channel error {response.status_code}")
        return response.json()

    def public_keys(self) -> dict[str, str]:
        return self._get("/keys")

    def credential(self, ifsc: str, fdr_no: str) -> dict:
        return self._get("/credentials", {"ifsc": ifsc, "fdr_no": fdr_no})

    def status(self, ifsc: str, fdr_no: str) -> dict:
        return self._get("/status", {"ifsc": ifsc, "fdr_no": fdr_no})

    def remove_lien(self, ifsc: str, fdr_no: str) -> dict:
        try:
            response = httpx.post(
                f"{self.base}/lien/remove",
                json={"ifsc": ifsc, "fdr_no": fdr_no},
                headers=self.headers,
                timeout=10,
            )
        except httpx.HTTPError as exc:
            raise BankChannelError(f"bank channel unreachable: {exc}") from exc
        if response.status_code != 200:
            raise BankChannelError(f"lien removal failed ({response.status_code})")
        return response.json()
