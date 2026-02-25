import hashlib
import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import QueryCache


def make_query_key(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached_result(db: Session, query_key: str) -> Optional[Dict[str, Any]]:
    cached = db.query(QueryCache).filter(QueryCache.query_key == query_key).first()
    if not cached:
        return None
    return json.loads(cached.response_json)


def upsert_cache_result(db: Session, query_key: str, response_json: Dict[str, Any]) -> None:
    payload = json.dumps(response_json, ensure_ascii=False)
    cached = db.query(QueryCache).filter(QueryCache.query_key == query_key).first()
    if cached:
        cached.response_json = payload
    else:
        cached = QueryCache(query_key=query_key, response_json=payload)
        db.add(cached)
    db.commit()
