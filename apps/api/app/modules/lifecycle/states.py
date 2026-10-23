"""Instrument states and trust levels (plan §7.1 and N1)."""

from enum import IntEnum, StrEnum


class InstrumentState(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    SCRUTINY = "scrutiny"
    DISCREPANCY = "discrepancy"
    REJECTED = "rejected"
    VERIFIED = "verified"
    ACTIVE = "active"
    EXPIRING = "expiring"
    OVERDUE = "overdue"
    RENEWED = "renewed"
    MATURED = "matured"
    RELEASING = "releasing"
    RELEASED = "released"
    ARCHIVED = "archived"


class TrustLevel(IntEnum):
    """Trust Ladder: who vouches for a value. Higher is stronger."""

    DECLARED = 0  # typed or uploaded by the institution
    MACHINE_CHECKED = 1  # extraction agrees, rules pass, forgery signals low
    OFFICER_VERIFIED = 2  # a named officer confirmed it
    BANK_ATTESTED = 3  # bank-signed credential or authorised bank channel matches
    LIVE_CONFIRMED = 4  # bank confirms current status within its freshness window


class InstrumentKind(StrEnum):
    """Kinds the data model can store. Which kinds AICTE accepts is an open question
    (plan §14, Q3) and is enforced by policy configuration, not by this enum."""

    FDR = "fdr"
    SECURITY_DEPOSIT = "security_deposit"
    BANK_GUARANTEE = "bank_guarantee"
    DEMAND_DRAFT = "demand_draft"
    OTHER = "other"
