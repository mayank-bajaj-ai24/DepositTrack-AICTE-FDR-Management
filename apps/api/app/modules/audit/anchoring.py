"""Periodic Merkle anchoring of new audit events (N4).

Each anchor stores a Merkle root over a batch of events in the `anchor` table. The batch is
recorded as `anchor_event` rows (event id and leaf position), so verification hashes exactly
the events that were anchored, never a timestamp range.

When immudb is enabled the root is also written to immudb. Verification reads it back with a
verified get and compares it with the root recomputed from the events, so an insider who edits
the events and the anchor row together is still detected.
"""

import importlib.util
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import utcnow
from app.models import Anchor, AnchorEvent, Event
from app.modules.audit.hashchain import event_hash, merkle_root
from app.modules.audit.service import event_payload

logger = logging.getLogger("depositrack.anchoring")

CLIENT_MODULE = "immudb"
KEY_PREFIX = "depositrack:anchor:"
INSTALL_HINT = 'install it with `pip install -e ".[anchoring]"` in apps/api'


def client_installed() -> bool:
    """Is the optional immudb client importable? Checked without importing it."""
    return importlib.util.find_spec(CLIENT_MODULE) is not None


@dataclass(frozen=True)
class ImmudbStatus:
    enabled: bool
    client_installed: bool

    @property
    def problem(self) -> str | None:
        """Why anchoring cannot write receipts although it is configured to."""
        if self.enabled and not self.client_installed:
            return (
                "DT_IMMUDB_ENABLED is true but the immudb client is not installed; " + INSTALL_HINT
            )
        return None


def immudb_status(settings: Settings) -> ImmudbStatus:
    return ImmudbStatus(enabled=settings.immudb_enabled, client_installed=client_installed())


class ReceiptError(Exception):
    """immudb is off, unreachable, refused the login or failed the request."""


class ReceiptProofError(ReceiptError):
    """immudb answered, but the entry or its cryptographic proof does not check out."""


def _load_client_module():
    """Import the optional client only when it is used (tests replace this with a fake)."""
    import immudb
    import immudb.exceptions

    return immudb


def _describe(exc: Exception) -> str:
    details = getattr(exc, "details", None)  # grpc.RpcError carries the server's message here
    text = details() if callable(details) else str(exc)
    lines = (text or "").strip().splitlines()
    return lines[0][:300] if lines else type(exc).__name__


class ImmudbStore:
    """One immudb session, opened on first use and reused for the rest of a request."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._module = None
        self._client = None
        self._failure: ReceiptError | None = None
        status = immudb_status(settings)
        if not status.enabled:
            self._failure = ReceiptError("immudb is disabled (DT_IMMUDB_ENABLED=false)")
        elif status.problem:
            self._failure = ReceiptError(status.problem)

    def __enter__(self) -> "ImmudbStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _fail(self, message: str) -> ReceiptError:
        self._failure = ReceiptError(message)  # later calls fail fast instead of timing out
        return self._failure

    def _connect(self):
        if self._failure is not None:
            raise self._failure
        if self._client is None:
            s = self._settings
            try:
                module = _load_client_module()
            except ImportError as exc:
                raise self._fail(
                    f"The immudb client could not be imported ({_describe(exc)}); {INSTALL_HINT}"
                ) from exc
            try:
                client = module.ImmudbClient(
                    f"{s.immudb_host}:{s.immudb_port}", timeout=s.immudb_timeout_seconds
                )
                client.login(s.immudb_user, s.immudb_password)
            except Exception as exc:  # refused connection, timeout, wrong password
                raise self._fail(
                    f"Could not log in to immudb at {s.immudb_host}:{s.immudb_port} as "
                    f"{s.immudb_user!r}: {_describe(exc)}. Check that immudb is running and that "
                    "DT_IMMUDB_PASSWORD matches IMMUDB_ADMIN_PASSWORD in infra/.env"
                ) from exc
            self._module, self._client = module, client
        return self._client

    def put(self, key: str, value: str) -> str:
        """Write with a verified set; return the immudb transaction id."""
        client = self._connect()
        try:
            result = client.verifiedSet(key.encode(), value.encode())
        except Exception as exc:
            raise ReceiptError(f"immudb write failed: {_describe(exc)}") from exc
        return str(result.id)

    def get_at(self, key: str, tx: int) -> str:
        """Read a key as of a transaction with a verified get; return its value."""
        client = self._connect()
        corrupted = self._module.exceptions.ErrCorruptedData
        try:
            result = client.verifiedGetAt(key.encode(), tx)
        except corrupted as exc:
            raise ReceiptProofError(f"immudb proof for tx {tx} did not verify") from exc
        except Exception as exc:
            reason = _describe(exc)
            if "not found" in reason.lower():  # logged in fine, but immudb has no such entry
                raise ReceiptProofError(f"immudb has no entry for {key} at tx {tx}") from exc
            raise ReceiptError(f"immudb read failed: {reason}") from exc
        if not result.verified or result.key != key.encode():
            raise ReceiptProofError(f"immudb returned an unverified or different entry at tx {tx}")
        return result.value.decode()

    def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                client.logout()
            except Exception as exc:  # the session is discarded either way
                logger.debug("immudb logout failed: %s", _describe(exc))


def anchor_key(anchor: Anchor) -> str:
    return f"{KEY_PREFIX}{anchor.id}"


def _utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def anchor_new_events(session: Session) -> Anchor | None:
    """Store a Merkle root over every event that is not in an anchor yet. The caller commits.

    Membership, not `ts`, decides what is new: an event committed after the previous anchor
    but with an older or equal timestamp still goes into this batch, and no event is in two.
    """
    already_anchored = exists().where(AnchorEvent.event_id == Event.id)
    events = list(
        session.scalars(
            select(Event).where(~already_anchored).order_by(Event.ts, Event.seq, Event.id)
        )
    )
    if not events:
        return None
    anchor = Anchor(
        id=uuid.uuid4(),
        batch_start=_utc(events[0].ts),
        batch_end=_utc(events[-1].ts),
        merkle_root=merkle_root([e.hash for e in events]),
        ts=utcnow(),
    )
    session.add(anchor)
    session.flush()
    session.add_all(
        AnchorEvent(event_id=e.id, anchor_id=anchor.id, position=position)
        for position, e in enumerate(events)
    )
    session.flush()
    return anchor


def write_receipt(anchor: Anchor, store: ImmudbStore) -> None:
    """Write the anchor's root to immudb and record the tx, or why it failed.

    Call after the anchor row is committed, so the anchor survives an immudb outage and
    immudb never holds a root that no anchor row points to. The caller commits again.
    """
    anchor.store_key = anchor_key(anchor)
    try:
        anchor.store_tx = store.put(anchor.store_key, anchor.merkle_root)
        anchor.store_error = None
    except ReceiptError as exc:
        anchor.store_tx = None
        anchor.store_error = str(exc)
        logger.warning("Anchor %s stored without an immudb receipt: %s", anchor.id, exc)


ReceiptStatus = Literal["verified", "mismatch", "none", "unchecked"]


@dataclass(frozen=True)
class AnchorCheck:
    """Result of checking one anchor.

    root_matches: the anchored events, re-hashed, give the root stored on the anchor row.
    receipt: "verified" (immudb holds the recomputed root), "mismatch" (it does not, or its
    proof fails), "none" (no external receipt was written) or "unchecked" (immudb is off or
    unreachable, so only the local check ran).
    """

    root_matches: bool
    receipt: ReceiptStatus
    detail: str

    @property
    def valid(self) -> bool:
        return self.root_matches and self.receipt != "mismatch"


def recompute_root(session: Session, anchor: Anchor) -> str:
    """Recompute every event hash from the row's contents, then the batch's Merkle root.

    The stored `hash` column is not trusted: an insider could edit a row and its hash together.
    """
    events = session.scalars(
        select(Event)
        .join(AnchorEvent, AnchorEvent.event_id == Event.id)
        .where(AnchorEvent.anchor_id == anchor.id)
        .order_by(AnchorEvent.position)
    )
    return merkle_root([event_hash(e.prev_hash, event_payload(e)) for e in events])


def verify_anchor(
    session: Session, anchor: Anchor, store: ImmudbStore | None = None
) -> AnchorCheck:
    """Check the anchor against its events and, when it has one, its immudb receipt."""
    root = recompute_root(session, anchor)
    root_matches = root == anchor.merkle_root
    if anchor.store_tx is None:
        detail = "No external receipt"
        if anchor.store_error:
            detail += f"; the immudb write failed: {anchor.store_error}"
        return AnchorCheck(root_matches, "none", detail)
    if store is None:
        return AnchorCheck(root_matches, "unchecked", "immudb receipt not checked")
    try:
        tx = int(anchor.store_tx)
    except ValueError:
        return AnchorCheck(root_matches, "mismatch", "The receipt's immudb tx is not a number")
    try:
        held = store.get_at(anchor.store_key or anchor_key(anchor), tx)
    except ReceiptProofError as exc:
        return AnchorCheck(root_matches, "mismatch", str(exc))
    except ReceiptError as exc:
        return AnchorCheck(root_matches, "unchecked", str(exc))
    if held != root:
        return AnchorCheck(root_matches, "mismatch", f"immudb tx {tx} holds a different root")
    return AnchorCheck(root_matches, "verified", f"Root matches immudb tx {tx}")
