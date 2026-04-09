from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_run_id(timestamp: str | None = None) -> str:
    raw = timestamp or utc_now_iso()
    return raw.replace(":", "-")
