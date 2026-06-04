from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.match_schema import StandingRead
from app.services.match_service import get_group_standings, get_groups


router = APIRouter(tags=["groups"])


@router.get("/groups", response_model=list[str])
def list_groups(db: Session = Depends(get_db)) -> list[str]:
    return get_groups(db)


@router.get("/groups/{group_name}/standings", response_model=list[StandingRead])
def read_group_standings(group_name: str, db: Session = Depends(get_db)) -> list[StandingRead]:
    return get_group_standings(db, group_name)
