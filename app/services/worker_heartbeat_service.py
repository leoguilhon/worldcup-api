from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.worker_heartbeat import WorkerHeartbeat


def touch_worker_heartbeat(db: Session, name: str) -> WorkerHeartbeat:
    heartbeat = db.get(WorkerHeartbeat, name)
    if not heartbeat:
        heartbeat = WorkerHeartbeat(name=name, last_seen_at=datetime.now(timezone.utc))
        db.add(heartbeat)
    else:
        heartbeat.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return heartbeat
