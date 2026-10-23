"""ORM models. Importing this package registers every table on Base.metadata."""

from app.models.account import UserAccount
from app.models.audit import Anchor, Event
from app.models.document import Attestation, Document
from app.models.institution import Institution
from app.models.instrument import Bank, BankMerger, FieldValue, IfscLineage, Instrument
from app.models.notification import Notification
from app.models.obligation import Coverage, Obligation
from app.models.policy import FieldPermission, PolicyVersion
from app.models.review import Case, Flag, Observation
from app.models.setting import SystemSetting

__all__ = [
    "Anchor",
    "Attestation",
    "Bank",
    "BankMerger",
    "Case",
    "Coverage",
    "Document",
    "Event",
    "FieldPermission",
    "FieldValue",
    "Flag",
    "IfscLineage",
    "Institution",
    "Instrument",
    "Notification",
    "Obligation",
    "Observation",
    "PolicyVersion",
    "SystemSetting",
    "UserAccount",
]
