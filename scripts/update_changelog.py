#!/usr/bin/env python3
"""Append weekly changelog entry for site data refresh."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MAX_ENTRIES = 16


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    changelog_path = base / "site" / "data" / "changelog.json"
    changelog_path.parent.mkdir(parents=True, exist_ok=True)

    current = read_json(changelog_path, [])
    now = datetime.now(timezone.utc)
    entry = {
        "date": now.strftime("%Y-%m-%d"),
        "title": "Atualização automática semanal",
        "summary": "Dados e métricas recalculados a partir dos CSV mais recentes.",
        "generatedAt": now.isoformat(),
    }

    if current and current[0].get("date") == entry["date"]:
        current[0] = entry
    else:
        current.insert(0, entry)

    changelog_path.write_text(
        json.dumps(current[:MAX_ENTRIES], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(changelog_path)


if __name__ == "__main__":
    main()
