from __future__ import annotations

from sqlalchemy.orm import Session

from .models import ActivityEvent


def log(db: Session, actor_id: str | None, action: str, entity_type: str = "", entity_id: str = "", **detail) -> None:
    db.add(ActivityEvent(actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id, detail=detail))
