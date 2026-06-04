from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.team import Team
from app.schemas.team_schema import TeamRead


router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamRead])
def list_teams(include_placeholders: bool = False, db: Session = Depends(get_db)) -> list[Team]:
    stmt = select(Team).order_by(Team.name.asc())
    if not include_placeholders:
        stmt = stmt.where(Team.is_placeholder.is_(False))
    return list(db.scalars(stmt))


@router.get("/{team_id}", response_model=TeamRead)
def get_team(team_id: int, db: Session = Depends(get_db)) -> Team:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team
