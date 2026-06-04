from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.match import Match, MatchCompetition, MatchStatus
from app.models.match_event import MatchEvent
from app.schemas.match_event_schema import MatchEventRead
from app.schemas.match_schema import MatchDetail, MatchRead
from app.services.match_service import get_live_matches, get_match, get_matches, get_todays_matches


router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("", response_model=list[MatchRead])
def list_matches(
    status: MatchStatus | None = None,
    competition: MatchCompetition | None = None,
    group_name: str | None = None,
    stage: str | None = None,
    date_filter: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
) -> list[Match]:
    return get_matches(
        db,
        status=status,
        competition=competition,
        group_name=group_name,
        stage=stage,
        match_date=date_filter,
    )


@router.get("/today", response_model=list[MatchRead])
def list_today_matches(db: Session = Depends(get_db)) -> list[Match]:
    return get_todays_matches(db)


@router.get("/live", response_model=list[MatchRead])
def list_live_matches(db: Session = Depends(get_db)) -> list[Match]:
    return get_live_matches(db)


@router.get("/{match_id}", response_model=MatchDetail)
def read_match(match_id: int, db: Session = Depends(get_db)) -> Match:
    match = get_match(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@router.get("/{match_id}/events", response_model=list[MatchEventRead])
def read_match_events(match_id: int, db: Session = Depends(get_db)) -> list[MatchEvent]:
    match = db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    stmt = select(MatchEvent).where(MatchEvent.match_id == match_id).order_by(MatchEvent.minute.asc())
    return list(db.scalars(stmt))
