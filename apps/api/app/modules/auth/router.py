from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.core.security import Principal, get_current_principal, permissions_of
from app.db.session import get_session
from app.models import Institution, UserAccount

router = APIRouter(prefix="/api/v1", tags=["auth"])


class MeResponse(BaseModel):
    subject: str
    username: str
    roles: list[str]
    permissions: list[str]
    # The account's own links, so the UI never guesses the institution from a list it can
    # see (an officer who is also an institution sees their region's institutions too).
    institution: dict | None = None
    region: str | None = None
    bank_code: str | None = None


@router.get("/me", response_model=MeResponse)
def me(
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> MeResponse:
    """Who is calling, with their DepositTrack roles, the actions those roles allow, and the
    institution, region and bank their account is linked to."""
    account = session.scalars(
        select(UserAccount).where(UserAccount.username == principal.username)
    ).first()
    own = (
        session.get(Institution, account.institution_id)
        if account and account.institution_id
        else None
    )
    return MeResponse(
        subject=principal.subject,
        username=principal.username,
        roles=sorted(principal.roles),
        permissions=permissions_of(principal),
        institution=ser.institution(own),
        region=account.region if account else None,
        bank_code=account.bank_code if account else None,
    )
