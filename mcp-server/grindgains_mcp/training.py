from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from .errors import GrindGainsError

DEFAULT_TIMEZONE = "America/Halifax"

# Same rule as the API (src/app.py MOVEMENT_ID_RE), checked before any request is made.
MOVEMENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

Number = int | float


class Movement(BaseModel):
    movement_id: str
    display_name: str
    mode: Literal["isotonic", "mobeta"] = Field(
        description="isotonic = sets x reps with a load; mobeta = timed isometric hold"
    )
    entry_count: int = Field(description="Number of logged sets or holds")
    last_logged_date_local: str = Field(description="YYYY-MM-DD in the configured local timezone")


class TrainingEntry(BaseModel):
    timestamp: str = Field(description="ISO-8601 with the local UTC offset")
    date_local: str = Field(description="YYYY-MM-DD in the configured local timezone")
    mode: Literal["isotonic", "mobeta"]
    weight_lb: Number = Field(description="Load in pounds (added weight for mobeta holds)")
    reps: Number | None = Field(description="Repetitions in this set (isotonic only, otherwise null)")
    hold_seconds: Number | None = Field(description="Hold time in seconds (mobeta only, otherwise null)")
    sets: Number = Field(description="Number of sets this entry represents")
    rpe: Number | None = Field(description="Rate of perceived exertion 1-10, null when not recorded")


def get_timezone(name: str | None = None) -> ZoneInfo:
    chosen = name or os.environ.get("GRINDGAINS_TZ") or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(chosen)
    except (ZoneInfoNotFoundError, ValueError):
        raise GrindGainsError(
            f"Unknown timezone {chosen!r}. Set GRINDGAINS_TZ to an IANA name such as {DEFAULT_TIMEZONE}."
        ) from None


def validate_movement_id(movement_id: object) -> str:
    if not isinstance(movement_id, str) or not MOVEMENT_ID_RE.match(movement_id):
        raise GrindGainsError("movement_id must be 1-128 characters: letters, digits, underscore, or hyphen")
    return movement_id


def humanize_movement_id(movement_id: str) -> str:
    return " ".join(word[0].upper() + word[1:] for word in re.split(r"[_-]", movement_id) if word)


def to_local(timestamp: str, zone: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone)


def to_entry(raw: dict, zone: ZoneInfo) -> TrainingEntry:
    local = to_local(raw["timestamp"], zone)
    is_hold = raw["mode"] == "mobeta"
    return TrainingEntry(
        timestamp=local.isoformat(),
        date_local=local.date().isoformat(),
        mode=raw["mode"],
        weight_lb=raw["weight"],
        reps=None if is_hold else raw["reps_or_time"],
        hold_seconds=raw["reps_or_time"] if is_hold else None,
        sets=raw["sets"],
        rpe=raw.get("rpe"),
    )


def to_entries(raw_rows: list[dict], zone: ZoneInfo) -> list[TrainingEntry]:
    """Oldest first, regardless of the order the API returned."""
    ordered = sorted(raw_rows, key=lambda row: to_local(row["timestamp"], zone))
    return [to_entry(row, zone) for row in ordered]


def to_movement(movement_id: str, raw_history: list[dict], zone: ZoneInfo) -> Movement:
    entries = to_entries(raw_history, zone)
    latest = entries[-1]
    return Movement(
        movement_id=movement_id,
        display_name=humanize_movement_id(movement_id),
        mode=latest.mode,
        entry_count=len(entries),
        last_logged_date_local=latest.date_local,
    )
