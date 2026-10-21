from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import Principal, get_current_principal, permissions_of

router = APIRouter(prefix="/api/v1", tags=["auth"])


class MeResponse(BaseModel):
    subject: str
    username: str
    roles: list[str]
    permissions: list[str]


@router.get("/me", response_model=MeResponse)
def me(principal: Principal = Depends(get_current_principal)) -> MeResponse:
    """Who is calling, with their DepositTrack roles and the actions those roles allow."""
    return MeResponse(
        subject=principal.subject,
        username=principal.username,
        roles=sorted(principal.roles),
        permissions=permissions_of(principal),
    )
