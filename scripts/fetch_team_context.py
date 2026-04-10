#!/usr/bin/env python3
"""
Fetch team availability context (injuries/suspensions + probable formation when available)
from API-Football and store in site/data/team-context.json.

Requires env var API_FOOTBALL_KEY.
If missing or request fails, writes an empty but valid payload.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://v3.football.api-sports.io"

# Local league code -> API-Football league id
LEAGUE_ID_MAP = {
    "E0": 39,    # Premier League
    "E1": 40,    # Championship
    "F1": 61,    # Ligue 1
    "I1": 135,   # Serie A
    "P1": 94,    # Liga Portugal
    "D1": 78,    # Bundesliga
    "SP1": 140,  # La Liga
    "SC0": 179,  # Scottish Premiership
    "N1": 88,    # Eredivisie
    "T1": 203,   # Super Lig
}


def season_for_today() -> int:
    now = datetime.now(timezone.utc)
    # Most EU football seasons switch around July/Aug.
    return now.year if now.month >= 7 else now.year - 1


def api_get(path: str, params: dict, api_key: str) -> dict:
    qs = urlencode(params)
    url = f"{BASE_URL}{path}?{qs}"
    req = Request(
        url,
        headers={
            "x-apisports-key": api_key,
            "User-Agent": "radar-equipas/1.0",
        },
    )
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize_team_name(name: str | None) -> str:
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


def upsert_team(ctx: dict, league: str, team_name: str) -> dict:
    by_league = ctx.setdefault(league, {})
    item = by_league.setdefault(
        team_name,
        {
            "team": team_name,
            "unavailableCount": 0,
            "injuryCount": 0,
            "suspensionCount": 0,
            "keyAbsences": [],
            "probableFormation": None,
            "formationFixtureDate": None,
        },
    )
    return item


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    out_path = base / "site" / "data" / "team-context.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    api_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    season = season_for_today()
    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "meta": {
            "provider": "api-football",
            "generatedAt": now_iso,
            "season": season,
            "keyConfigured": bool(api_key),
        },
        "teamContextByLeague": {},
        "errors": [],
    }

    if not api_key:
        payload["errors"].append("Missing API_FOOTBALL_KEY. Team context not fetched.")
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(out_path)
        return

    try:
        # Injuries + suspensions by league
        for league_code, league_id in LEAGUE_ID_MAP.items():
            try:
                inj = api_get("/injuries", {"league": league_id, "season": season}, api_key)
                for row in inj.get("response", []) or []:
                    team = ((row.get("team") or {}).get("name")) or ""
                    player = ((row.get("player") or {}).get("name")) or "Jogador"
                    kind = str((row.get("type") or "")).strip() or "Injury"
                    reason = str((row.get("reason") or "")).strip() or "N/A"
                    if not team:
                        continue
                    item = upsert_team(payload["teamContextByLeague"], league_code, team)
                    item["unavailableCount"] += 1
                    if "susp" in kind.lower():
                        item["suspensionCount"] += 1
                    else:
                        item["injuryCount"] += 1
                    if len(item["keyAbsences"]) < 5:
                        item["keyAbsences"].append(
                            {"player": player, "type": kind, "reason": reason}
                        )
            except (HTTPError, URLError) as ex:
                payload["errors"].append(f"{league_code}: injuries unavailable ({ex})")

        # Probable formation from predictions on next fixtures
        for league_code, league_id in LEAGUE_ID_MAP.items():
            try:
                fx = api_get("/fixtures", {"league": league_id, "season": season, "next": 20}, api_key)
                fixtures = fx.get("response", []) or []
                for f in fixtures[:12]:
                    fixture_id = ((f.get("fixture") or {}).get("id"))
                    fixture_date = ((f.get("fixture") or {}).get("date"))
                    if not fixture_id:
                        continue
                    try:
                        pr = api_get("/predictions", {"fixture": fixture_id}, api_key)
                        resp = pr.get("response", []) or []
                        if not resp:
                            continue
                        pred = resp[0] if isinstance(resp[0], dict) else {}
                        lineups = pred.get("predictions", {}).get("lineups", {}) or {}
                        teams = pred.get("teams", {}) or {}
                        home_team = (teams.get("home") or {}).get("name")
                        away_team = (teams.get("away") or {}).get("name")
                        home_form = lineups.get("home")
                        away_form = lineups.get("away")
                        if home_team and home_form:
                            item = upsert_team(payload["teamContextByLeague"], league_code, home_team)
                            if item.get("probableFormation") is None:
                                item["probableFormation"] = str(home_form)
                                item["formationFixtureDate"] = fixture_date
                        if away_team and away_form:
                            item = upsert_team(payload["teamContextByLeague"], league_code, away_team)
                            if item.get("probableFormation") is None:
                                item["probableFormation"] = str(away_form)
                                item["formationFixtureDate"] = fixture_date
                    except (HTTPError, URLError):
                        continue
            except (HTTPError, URLError) as ex:
                payload["errors"].append(f"{league_code}: fixtures/predictions unavailable ({ex})")

        # Normalized aliases map for frontend matching fallback
        norm_by_league = {}
        for league_code, teams in payload["teamContextByLeague"].items():
            norm_by_league[league_code] = {}
            for team_name, entry in teams.items():
                norm_by_league[league_code][normalize_team_name(team_name)] = entry
        payload["teamContextByLeagueNorm"] = norm_by_league

    except Exception as ex:
        payload["errors"].append(f"Unexpected error: {type(ex).__name__}: {ex}")

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()

