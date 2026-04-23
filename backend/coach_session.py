"""
Maç analizi sonrası kısa sohbet: Redis'te oturum bağlamı + son N mesaj.
"""
import json
import os

import redis

_COACH_CTX_PREFIX = "coach_match_ctx:"
_COACH_HIST_PREFIX = "coach_chat_hist:"


def _client() -> redis.Redis:
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        db=int(os.getenv("REDIS_DB", 0)),
        decode_responses=True,
    )


def _ttl_sec() -> int:
    return int(os.getenv("COACH_SESSION_TTL_SEC", "86400"))


def _max_chat_messages() -> int:
    # Varsayılan: 12 satır = 6 kullanıcı + 6 asistan (yaklaşık 6 tur)
    return max(4, int(os.getenv("COACH_CHAT_MAX_MESSAGES", "12")))


def save_analysis_snapshot(session_id: str, params: dict, analysis_text: str) -> None:
    if not session_id:
        return
    r = _client()
    payload = {
        "match_id": params.get("match_id"),
        "home_id": params.get("home_id"),
        "away_id": params.get("away_id"),
        "my_team_id": params.get("my_team_id"),
        "match_date": params.get("match_date"),
        "analysis_snapshot": (analysis_text or "")[:20000],
    }
    r.setex(
        f"{_COACH_CTX_PREFIX}{session_id}",
        _ttl_sec(),
        json.dumps(payload, ensure_ascii=False),
    )


def load_match_context(session_id: str) -> dict | None:
    if not session_id:
        return None
    raw = _client().get(f"{_COACH_CTX_PREFIX}{session_id}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def get_chat_history(session_id: str) -> list[dict]:
    if not session_id:
        return []
    raw = _client().get(f"{_COACH_HIST_PREFIX}{session_id}")
    if not raw:
        return []
    try:
        h = json.loads(raw)
        return h if isinstance(h, list) else []
    except json.JSONDecodeError:
        return []


def append_chat_turn(session_id: str, user_msg: str, assistant_msg: str) -> list[dict]:
    if not session_id:
        return []
    r = _client()
    hist = get_chat_history(session_id)
    hist.append({"role": "user", "content": (user_msg or "").strip()})
    hist.append({"role": "assistant", "content": (assistant_msg or "").strip()})
    cap = _max_chat_messages()
    if len(hist) > cap:
        hist = hist[-cap:]
    ttl = _ttl_sec()
    r.setex(
        f"{_COACH_HIST_PREFIX}{session_id}",
        ttl,
        json.dumps(hist, ensure_ascii=False),
    )
    return hist
