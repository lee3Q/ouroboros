#!/usr/bin/env python3
"""Export submitted-answer character evidence, never inferred human effort.

Read-only JSONL summaries. Older or malformed counts remain unknown. This is
not decision, host-visible turn, keystroke, or first-Seed measurement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import quote

from ouroboros.config.models import resolve_event_store_path


def export_counts(connection: sqlite3.Connection) -> list[dict[str, object]]:
    """Aggregate only persisted exact counts; never count preview lengths."""
    groups: dict[str, dict[str, object]] = {}
    rows = connection.execute(
        "SELECT aggregate_id, payload FROM events "
        "WHERE aggregate_type = 'interview' AND event_type = 'interview.response.recorded' "
        "ORDER BY aggregate_id, timestamp, id"
    )
    for identity, raw_payload in rows:
        key = hashlib.sha256(f"ouroboros-interview:{identity}".encode()).hexdigest()
        record = groups.setdefault(
            key,
            {
                "interview_id_sha256": key,
                "recorded_response_events": 0,
                "known_response_chars": 0,
                "unknown_response_events": 0,
                "response_chars_total": None,
            },
        )
        record["recorded_response_events"] += 1
        try:
            payload = json.loads(raw_payload)
        except (TypeError, ValueError, UnicodeError):
            payload = None
        count = payload.get("response_chars") if isinstance(payload, dict) else None
        if type(count) is int and count >= 0:
            record["known_response_chars"] += count
        else:
            record["unknown_response_events"] += 1
    for record in groups.values():
        if record["unknown_response_events"] == 0:
            record["response_chars_total"] = record["known_response_chars"]
    return list(groups.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()
    try:
        path = (args.db if args.db is not None else resolve_event_store_path()).expanduser()
        uri = f"file:{quote(path.resolve().as_posix(), safe='/:')}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            records = export_counts(connection)
        for record in records:
            print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    except (OSError, RuntimeError, ValueError, sqlite3.Error, UnicodeError):
        print("export_interview_effort: unable to read EventStore", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
