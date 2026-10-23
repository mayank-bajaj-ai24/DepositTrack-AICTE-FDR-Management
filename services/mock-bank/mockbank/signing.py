"""Per-bank Ed25519 keys and canonical-JSON signatures."""

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mockbank.files import locked, read_bytes, write_atomic


def canonical_json(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class KeyStore:
    """One signing key per bank code (first four IFSC letters), created on first use."""

    def __init__(self, keys_dir: str | Path):
        self.dir = Path(keys_dir)

    def _private(self, bank_code: str) -> Ed25519PrivateKey:
        path = self.dir / f"{bank_code.upper()}.pem"
        pem = read_bytes(path)
        if pem is None:
            # Create under the lock and swap in atomically: a published (and pinned) key must
            # never be replaced by a second key created concurrently by another thread or process.
            with locked(self.dir / "keys"):
                pem = read_bytes(path)
                if pem is None:
                    pem = Ed25519PrivateKey.generate().private_bytes(
                        serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption(),
                    )
                    write_atomic(path, pem)
        return serialization.load_pem_private_key(pem, password=None)

    def key_id(self, bank_code: str) -> str:
        return f"bank:{bank_code.upper()}:key-1"

    def public_b64(self, bank_code: str) -> str:
        raw = (
            self._private(bank_code)
            .public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        )
        return base64.b64encode(raw).decode()

    def sign(self, bank_code: str, payload: dict) -> str:
        return (
            "ed25519:"
            + base64.b64encode(self._private(bank_code).sign(canonical_json(payload))).decode()
        )

    def known_banks(self) -> list[str]:
        return sorted(p.stem for p in self.dir.glob("*.pem")) if self.dir.exists() else []
