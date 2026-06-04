from collections import defaultdict
from datetime import date, datetime, time, timezone

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.match import Match, MatchCompetition, MatchStatus
from app.models.team import Team
from app.schemas.match_schema import StandingRead


ACTIVE_MATCH_STATUSES = (MatchStatus.LIVE, MatchStatus.HALF_TIME, MatchStatus.EXTRA_TIME, MatchStatus.PENALTIES)


def get_matches(
    db: Session,
    *,
    status: MatchStatus | None = None,
    group_name: str | None = None,
    stage: str | None = None,
    match_date: date | None = None,
    competition: MatchCompetition | None = None,
) -> list[Match]:
    stmt = _match_query().order_by(Match.match_date.asc())

    if status == MatchStatus.LIVE:
        stmt = stmt.where(Match.status.in_(ACTIVE_MATCH_STATUSES))
    elif status:
        stmt = stmt.where(Match.status == status)
    if competition:
        stmt = stmt.where(Match.competition == competition)
    if group_name:
        stmt = stmt.where(Match.group_name == group_name)
    if stage:
        stmt = stmt.where(Match.stage == stage)
    if match_date:
        start = datetime.combine(match_date, time.min, tzinfo=timezone.utc)
        end = datetime.combine(match_date, time.max, tzinfo=timezone.utc)
        stmt = stmt.where(and_(Match.match_date >= start, Match.match_date <= end))

    return list(db.scalars(stmt).unique())


def get_match(db: Session, match_id: int) -> Match | None:
    return db.scalar(_match_query().where(Match.id == match_id))


def get_todays_matches(db: Session) -> list[Match]:
    return get_matches(db, match_date=datetime.now(timezone.utc).date())


def get_live_matches(db: Session) -> list[Match]:
    stmt = (
        _match_query()
        .where(Match.status.in_(ACTIVE_MATCH_STATUSES))
        .order_by(Match.match_date.asc())
    )
    return list(db.scalars(stmt).unique())


def get_groups(db: Session) -> list[str]:
    stmt = select(Match.group_name).where(Match.group_name.is_not(None)).distinct().order_by(Match.group_name)
    return [group for group in db.scalars(stmt) if group]


def get_group_standings(db: Session, group_name: str) -> list[StandingRead]:
    matches = get_matches(db, group_name=group_name, competition=MatchCompetition.WORLD_CUP)
    table: dict[int, dict[str, int | Team]] = {}

    for match in matches:
        if not match.home_team or not match.away_team:
            continue
        for team in (match.home_team, match.away_team):
            table.setdefault(
                team.id,
                {
                    "team": team,
                    "played": 0,
                    "won": 0,
                    "drawn": 0,
                    "lost": 0,
                    "goals_for": 0,
                    "goals_against": 0,
                    "points": 0,
                },
            )

        if match.status != MatchStatus.FINISHED:
            continue

        home_score = match.home_score or 0
        away_score = match.away_score or 0
        home = table[match.home_team.id]
        away = table[match.away_team.id]
        home["played"] += 1
        away["played"] += 1
        home["goals_for"] += home_score
        home["goals_against"] += away_score
        away["goals_for"] += away_score
        away["goals_against"] += home_score

        if home_score > away_score:
            home["won"] += 1
            home["points"] += 3
            away["lost"] += 1
        elif away_score > home_score:
            away["won"] += 1
            away["points"] += 3
            home["lost"] += 1
        else:
            home["drawn"] += 1
            away["drawn"] += 1
            home["points"] += 1
            away["points"] += 1

    standings = []
    for row in table.values():
        goals_for = int(row["goals_for"])
        goals_against = int(row["goals_against"])
        standings.append(
            StandingRead(
                team=row["team"],
                played=int(row["played"]),
                won=int(row["won"]),
                drawn=int(row["drawn"]),
                lost=int(row["lost"]),
                goals_for=goals_for,
                goals_against=goals_against,
                goal_difference=goals_for - goals_against,
                points=int(row["points"]),
            )
        )

    return sorted(
        standings,
        key=lambda item: (item.points, item.goal_difference, item.goals_for),
        reverse=True,
    )


def _match_query() -> Select[tuple[Match]]:
    return select(Match).options(
        joinedload(Match.home_team),
        joinedload(Match.away_team),
        joinedload(Match.winner_team),
        selectinload(Match.events),
    )
