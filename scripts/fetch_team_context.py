#!/usr/bin/env python3
"""
Fetch team availability context (injuries/suspensions + probable formation)
and fatigue/rotation context using multi-competition fixtures from API-Football.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://v3.football.api-sports.io"
LEAGUE_ID_MAP = {
    "E0": 39,
    "E1": 40,
    "F1": 61,
    "I1": 135,
    "P1": 94,
    "D1": 78,
    "SP1": 140,
    "SC0": 179,
    "N1": 88,
    "T1": 203,
}
EUROPE_HINTS = ("uefa", "champions league", "europa league", "conference league")


def season_for_today() -> int:
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 7 else now.year - 1


def api_get(path: str, params: dict, api_key: str) -> dict:
    qs = urlencode(params)
    url = f"{BASE_URL}{path}?{qs}"
    req = Request(
        url,
        headers={"x-apisports-key": api_key, "User-Agent": "radar-equipas/1.0"},
    )
    with urlopen(req, timeout=35) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    errs = payload.get("errors")
    if isinstance(errs, dict) and errs:
        err_text = "; ".join(f"{k}: {v}" for k, v in errs.items() if v)
        if err_text:
            raise ValueError(f"{path} -> {err_text}")
    return payload


def normalize_team_name(name: str | None) -> str:
    raw = str(name or "").strip().lower()
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    repl = {
        "'": "",
        ".": "",
        "-": " ",
        "_": " ",
        "&": " ",
        "/": " ",
        " fc": "",
        " cf": "",
        " ac": "",
        " sc": "",
        " afc": "",
        " cfc": "",
        " calcio": "",
        " clube de futebol": "",
        " futebol clube": "",
    }
    for a, b in repl.items():
        raw = raw.replace(a, b)
    raw = re.sub(r"\b(the|club|de|do|da|sv|vfl|tsg|rc|as|us|ssc|ss|cd|gd)\b", " ", raw)
    raw = re.sub(r"[^a-z0-9 ]", " ", raw)
    return " ".join(raw.split())


def add_team_alias(team_map: dict[str, dict], team_name: str | None, team_id: int | None) -> None:
    if not team_name or not team_id:
        return
    norm = normalize_team_name(team_name)
    if not norm:
        return
    item = {"id": int(team_id), "name": str(team_name)}
    team_map[norm] = item
    team_map[norm.replace(" ", "")] = item


def upsert_team(ctx: dict, league: str, team_name: str) -> dict:
    by_league = ctx.setdefault(league, {})
    return by_league.setdefault(
        team_name,
        {
            "team": team_name,
            "unavailableCount": 0,
            "injuryCount": 0,
            "suspensionCount": 0,
            "keyAbsences": [],
            "probableFormation": None,
            "formationFixtureDate": None,
            "fatigue": {},
        },
    )


def parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def is_played_status(short: str | None) -> bool:
    s = str(short or "").upper()
    return s in {"FT", "AET", "PEN", "BT", "AWD", "WO"}


def is_european_comp(name: str | None) -> bool:
    n = str(name or "").lower()
    return any(h in n for h in EUROPE_HINTS)


def resolve_team_id(api_key: str, league_id: int, season: int, team_name: str) -> tuple[int | None, str | None]:
    try:
        resp = api_get("/teams", {"league": league_id, "season": season, "search": team_name}, api_key)
    except (HTTPError, URLError, ValueError):
        resp = {}
    rows = resp.get("response", []) or []
    if not rows:
        try:
            resp2 = api_get("/teams", {"search": team_name}, api_key)
            rows = resp2.get("response", []) or []
        except (HTTPError, URLError, ValueError):
            rows = []
    if not rows:
        return None, None
    target = normalize_team_name(team_name)
    best = rows[0]
    for r in rows:
        nm = ((r.get("team") or {}).get("name")) or ""
        if normalize_team_name(nm) == target:
            best = r
            break
    team_obj = best.get("team") or {}
    return team_obj.get("id"), team_obj.get("name")


def lookup_team_id_from_map(team_map: dict, team_name: str) -> tuple[int | None, str | None]:
    n = normalize_team_name(team_name)
    if n in team_map:
        t = team_map[n]
        return t.get("id"), t.get("name")
    ns = n.replace(" ", "")
    if ns in team_map:
        t = team_map[ns]
        return t.get("id"), t.get("name")
    for k, t in team_map.items():
        if k in n or n in k:
            return t.get("id"), t.get("name")
    return None, None


def build_fatigue_for_team(
    api_key: str,
    team_id: int,
    local_league_id: int,
) -> dict:
    now = datetime.now(timezone.utc)
    d_from = (now - timedelta(days=10)).strftime("%Y-%m-%d")
    d_to = (now + timedelta(days=10)).strftime("%Y-%m-%d")

    try:
        fx = api_get("/fixtures", {"team": team_id, "from": d_from, "to": d_to}, api_key)
    except (HTTPError, URLError, ValueError):
        return {}

    fixtures = fx.get("response", []) or []
    parsed = []
    for f in fixtures:
        fobj = f.get("fixture") or {}
        lobj = f.get("league") or {}
        dt = parse_dt(fobj.get("date"))
        if not dt:
            continue
        parsed.append(
            {
                "dt": dt,
                "status": ((fobj.get("status") or {}).get("short")),
                "leagueId": lobj.get("id"),
                "leagueName": lobj.get("name"),
            }
        )
    if not parsed:
        return {}

    parsed.sort(key=lambda x: x["dt"])
    future = [x for x in parsed if x["dt"] >= now]
    past_played = [x for x in parsed if x["dt"] < now and is_played_status(x["status"])]

    if not future:
        return {}

    ref = None
    for x in future:
        if int(x.get("leagueId") or -1) == int(local_league_id):
            ref = x
            break
    if ref is None:
        ref = future[0]

    prev = past_played[-1] if past_played else None
    days_rest = None
    if prev is not None:
        days_rest = max(0, round((ref["dt"] - prev["dt"]).total_seconds() / 86400))

    window_start = ref["dt"] - timedelta(days=8)
    games_last_8d = [x for x in past_played if window_start <= x["dt"] < ref["dt"]]
    games_next_8d = [x for x in future if ref["dt"] < x["dt"] <= ref["dt"] + timedelta(days=8)]
    euro_before = any(is_european_comp(x.get("leagueName")) for x in games_last_8d)
    euro_after = any(is_european_comp(x.get("leagueName")) for x in games_next_8d)
    extra_time_recent = any(str(x.get("status") or "").upper() in {"AET", "PEN"} for x in games_last_8d)

    return {
        "referenceFixtureDate": ref["dt"].isoformat(),
        "daysRest": days_rest,
        "gamesLast8d": len(games_last_8d),
        "thirdGameIn8d": len(games_last_8d) >= 2,
        "europeanBefore": euro_before,
        "europeanAfter": euro_after,
        "extraTimeRecent": extra_time_recent,
    }


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    out_path = base / "site" / "data" / "team-context.json"
    fixtures_path = base / "site" / "data" / "fixtures-upcoming.json"
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
            "fixturesInputCount": 0,
            "teamsSearched": 0,
            "teamsResolved": 0,
            "fatigueBuilt": 0,
        },
        "teamContextByLeague": {},
        "errors": [],
    }

    if not api_key:
        payload["errors"].append("Missing API_FOOTBALL_KEY. Team context not fetched.")
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(out_path)
        return

    fixtures_payload = {}
    if fixtures_path.exists():
        try:
            fixtures_payload = json.loads(fixtures_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            fixtures_payload = {}
    fixtures = fixtures_payload.get("fixtures", []) or []
    payload["meta"]["fixturesInputCount"] = len(fixtures)

    try:
        league_team_id_map: dict[str, dict[str, dict]] = {}

        # 1) injuries/suspensions by league
        for league_code, league_id in LEAGUE_ID_MAP.items():
            league_map = league_team_id_map.setdefault(league_code, {})
            try:
                inj = api_get("/injuries", {"league": league_id, "season": season}, api_key)
                for row in inj.get("response", []) or []:
                    team = ((row.get("team") or {}).get("name")) or ""
                    if not team:
                        continue
                    item = upsert_team(payload["teamContextByLeague"], league_code, team)
                    player = ((row.get("player") or {}).get("name")) or "Jogador"
                    kind = str((row.get("type") or "")).strip() or "Injury"
                    reason = str((row.get("reason") or "")).strip() or "N/A"
                    item["unavailableCount"] += 1
                    if "susp" in kind.lower():
                        item["suspensionCount"] += 1
                    else:
                        item["injuryCount"] += 1
                    if len(item["keyAbsences"]) < 5:
                        item["keyAbsences"].append({"player": player, "type": kind, "reason": reason})
                    add_team_alias(league_map, team, (row.get("team") or {}).get("id"))
            except (HTTPError, URLError, ValueError) as ex:
                payload["errors"].append(f"{league_code}: injuries unavailable ({ex})")

        # 2) probable formation + map from domestic fixtures
        for league_code, league_id in LEAGUE_ID_MAP.items():
            league_map = league_team_id_map.setdefault(league_code, {})
            try:
                fx = api_get("/fixtures", {"league": league_id, "season": season, "next": 30}, api_key)
                for f in (fx.get("response", []) or [])[:20]:
                    teams_block = f.get("teams") or {}
                    for side in ("home", "away"):
                        tob = teams_block.get(side) or {}
                        add_team_alias(league_map, tob.get("name"), tob.get("id"))

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
                        if home_team and lineups.get("home"):
                            item = upsert_team(payload["teamContextByLeague"], league_code, home_team)
                            if item.get("probableFormation") is None:
                                item["probableFormation"] = str(lineups.get("home"))
                                item["formationFixtureDate"] = fixture_date
                        if away_team and lineups.get("away"):
                            item = upsert_team(payload["teamContextByLeague"], league_code, away_team)
                            if item.get("probableFormation") is None:
                                item["probableFormation"] = str(lineups.get("away"))
                                item["formationFixtureDate"] = fixture_date
                    except (HTTPError, URLError, ValueError):
                        continue
            except (HTTPError, URLError, ValueError) as ex:
                payload["errors"].append(f"{league_code}: fixtures/predictions unavailable ({ex})")

            # Fallback ID map from standings
            try:
                st = api_get("/standings", {"league": league_id, "season": season}, api_key)
                for row in st.get("response", []) or []:
                    standings = ((row.get("league") or {}).get("standings")) or []
                    for group in standings:
                        for line in group or []:
                            t = line.get("team") or {}
                            add_team_alias(league_map, t.get("name"), t.get("id"))
            except (HTTPError, URLError, ValueError):
                pass

        # 3) fatigue/rotation multi-competition for teams in upcoming fixtures
        team_cache = {}
        for f in fixtures:
            league_code = str(f.get("league") or "")
            if league_code not in LEAGUE_ID_MAP:
                continue
            league_id = LEAGUE_ID_MAP[league_code]
            for tname in (f.get("homeTeamApi"), f.get("awayTeamApi")):
                if not tname:
                    continue
                key = (league_code, normalize_team_name(tname))
                if key in team_cache:
                    continue

                payload["meta"]["teamsSearched"] += 1
                team_id, api_name = lookup_team_id_from_map(
                    league_team_id_map.get(league_code, {}),
                    str(tname),
                )
                if not team_id:
                    team_id, api_name = resolve_team_id(api_key, league_id, season, str(tname))
                team_cache[key] = (team_id, api_name or str(tname))

                item = upsert_team(payload["teamContextByLeague"], league_code, str(api_name or tname))
                if not team_id:
                    continue

                payload["meta"]["teamsResolved"] += 1
                fatigue = build_fatigue_for_team(api_key, int(team_id), league_id)
                item["fatigue"] = fatigue
                if fatigue:
                    payload["meta"]["fatigueBuilt"] += 1

        # normalized map
        norm_by_league = {}
        for league_code, teams in payload["teamContextByLeague"].items():
            norm_by_league[league_code] = {}
            for team_name, entry in teams.items():
                norm_by_league[league_code][normalize_team_name(team_name)] = entry
        payload["teamContextByLeagueNorm"] = norm_by_league

        payload["meta"]["leagueTeamMapSizes"] = {
            lg: len(mp) for lg, mp in league_team_id_map.items() if mp
        }

        total = sum(len(v) for v in payload["teamContextByLeague"].values())
        if total == 0:
            payload["errors"].append("API_FOOTBALL respondeu sem contexto de equipas para os parâmetros atuais.")
        elif payload["meta"]["teamsResolved"] == 0:
            payload["errors"].append("Nenhuma equipa foi resolvida para team_id; validar plano/cobertura da API_FOOTBALL.")
        elif payload["meta"]["fatigueBuilt"] == 0:
            payload["errors"].append("Sem bloco de fadiga multi-competição gerado; verificar cobertura da API para fixtures por equipa.")

    except Exception as ex:
        payload["errors"].append(f"Unexpected error: {type(ex).__name__}: {ex}")

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
