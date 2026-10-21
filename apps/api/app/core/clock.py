"""The system date. A demo offset (days) can move it forward to show maturities;
it can only be set while the demo policy is active, and every change is audited."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import SystemSetting

KEY = "demo_clock_offset_days"


def offset_days(session: Session) -> int:
    setting = session.get(SystemSetting, KEY)
    return int(setting.value.get("days", 0)) if setting else 0


def today(session: Session) -> date:
    return date.today() + timedelta(days=offset_days(session))


def set_offset(session: Session, days: int, username: str) -> None:
    setting = session.get(SystemSetting, KEY)
    if setting is None:
        session.add(SystemSetting(key=KEY, value={"days": days}, updated_by=username))
    else:
        setting.value = {"days": days}
        setting.updated_by = username
    session.flush()
