"""ORM models. Importing this package registers every table on Base.metadata."""

from app.models.audit import Anchor, Event
from app.models.document import Attestation, Document
from app.models.institution import Institution
from app.models.instrument import FieldValue, IfscLineage, Instrument
from app.models.obligation import Coverage, Obligation
from app.models.policy import FieldPermission, PolicyVersion
from app.models.review import Case, Flag, Observation

__all__ = [
    "Anchor",
    "Attestation",
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
    "Obligation",
    "Observation",
    "PolicyVersion",
]
