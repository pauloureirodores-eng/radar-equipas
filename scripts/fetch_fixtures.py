#!/usr/bin/env python3
"""
Fetch upcoming weekend fixtures by league and store in site/data/fixtures-upcoming.json.

Data source: football-data.org v4 API.
Requires env var FOOTBALL_DATA_API_TOKEN (optional; if missing, writes empty payload).
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = "https://api.football-data.org/v4"
OUT_REL_PATH = Path("site/data/fixtures-upcoming.json")

# Local league code -> football-data competition code
LEAGUE_COMP_MAP = {
    "E0": "PL",    # Premier League
    "E1": "ELC",   # Championship
    "F1": "FL1",   # Ligue 1
    "I1": "SA",    # Serie A
    "P1": "PPL",   # Liga Portugal
    "D1": "BL1",   # Bundesliga
    "SP1": "PD",   # La Liga
    "SC0": "SPL",  # Scottish Premiership
    "N1": "DED",   # Eredivisie
    "T1": "TSL",   # Super Lig
}


def weekend_window(today: date) -> tuple[date, date]:
    # 0=Mon ... 6=Sun
    wd = today.weekday()
    if wd <= 4:
        friday = today + timedelta(days=(4 - wd))
    else:
        friday = today + timedelta(days=(11 - wd))
    monday = friday + timedelta(days=3)
    return friday, monday


def fetch_competition_matches(
    token: str,
    competition_code: str,
    date_from: date,
    date_to: date,
) -> list[dict]:
    qs = urlencode(
        {
            "dateFrom": date_from.strftime("%Y-%m-%d"),
            "dateTo": date_to.strftime("%Y-%m-%d"),
            "status": "SCHEDULED,TIMED",
        }
    )
    url = f"{API_BASE}/competitions/{competition_code}/matches?{qs}"
    req = Request(url, headers={"X-Auth-Token": token, "User-Agent": "radar-equipas/1.0"})
    with urlopen(req, timeout=25) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("matches", []) or []


def normalized_name(name: str | None) -> str:
    raw = str(name or "").strip().lower()
    repl = {
        "'": "",
        ".": "",
        "-": " ",
        "_": " ",
        " fc": "",
        " cf": "",
        " ac": "",
        " sc": "",
    }
    for a, b in repl.items():
        raw = raw.replace(a, b)
    return " ".join(raw.split())


def extract_fixture_row(local_league: str, match: dict) -> dict:
    home = (match.get("homeTeam") or {}).get("name")
    away = (match.get("awayTeam") or {}).get("name")
    utc_date = match.get("utcDate")
    return {
        "league": local_league,
        "competitionCode": (match.get("competition") or {}).get("code"),
        "competitionName": (match.get("competition") or {}).get("name"),
        "matchId": match.get("id"),
        "status": match.get("status"),
        "utcDate": utc_date,
        "date": (utc_date or "")[:10] if utc_date else None,
        "homeTeamApi": home,
        "awayTeamApi": away,
        "homeTeamNorm": normalized_name(home),
        "awayTeamNorm": normalized_name(away),
    }


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    out_path = base / OUT_REL_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)

    token = os.getenv("FOOTBALL_DATA_API_TOKEN", "").strip()
    today = datetime.now(timezone.utc).date()
    date_from, date_to = weekend_window(today)

    payload = {
        "meta": {
            "provider": "football-data.org",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "windowDateFrom": date_from.strftime("%Y-%m-%d"),
            "windowDateTo": date_to.strftime("%Y-%m-%d"),
            "tokenConfigured": bool(token),
        },
        "fixtures": [],
        "errors": [],
    }

    if not token:
        payload["errors"].append("Missing FOOTBALL_DATA_API_TOKEN. Fixtures not fetched.")
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(out_path)
        return

    for local_league, comp_code in LEAGUE_COMP_MAP.items():
        try:
            matches = fetch_competition_matches(token, comp_code, date_from, date_to)
            for m in matches:
                payload["fixtures"].append(extract_fixture_row(local_league, m))
        except HTTPError as ex:
            payload["errors"].append(f"{local_league}/{comp_code}: HTTP {ex.code}")
        except URLError as ex:
            payload["errors"].append(f"{local_league}/{comp_code}: URL error {ex.reason}")
        except Exception as ex:
            payload["errors"].append(f"{local_league}/{comp_code}: {type(ex).__name__}: {ex}")

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()

