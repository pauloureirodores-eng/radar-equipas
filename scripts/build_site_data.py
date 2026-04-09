#!/usr/bin/env python3
"""
Builds site/data/site-data.json from analyzer outputs in ./output.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd


def records(df: pd.DataFrame) -> list[dict]:
    # pandas -> json to guarantee NaN/Inf become null
    return json.loads(df.to_json(orient="records", force_ascii=False))


def market_group(market: str) -> str:
    m = str(market or "").lower()
    if "canto" in m:
        return "cantos"
    if "btts" in m or "ambas marcam" in m:
        return "btts"
    if (
        "golo" in m
        or "casa marca" in m
        or "clean sheet" in m
        or "over 1.5" in m
        or "over 2.5" in m
        or "over 3.5" in m
        or "under 2.5" in m
    ):
        return "golos"
    if "vitoria" in m or "empate" in m or "1x2" in m or "handicap" in m:
        return "resultados"
    return "outros"


def safe_weighted_mean(values: pd.Series, weights: pd.Series) -> float | None:
    vals = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce")
    mask = vals.notna() & w.notna() & (w > 0)
    if not mask.any():
        return None
    return float((vals[mask] * w[mask]).sum() / w[mask].sum())


def build_backtest_rows(market_rows: pd.DataFrame) -> list[dict]:
    df = market_rows.copy()
    df["group"] = df["market"].map(market_group)
    out: list[dict] = []

    grouped = df.groupby(["league", "group"], dropna=False)
    for (league, group), g in grouped:
        bets = int(pd.to_numeric(g["jogos"], errors="coerce").fillna(0).sum())
        hit_rate = safe_weighted_mean(g["hit_rate"], g["jogos"])
        roi_mean = safe_weighted_mean(g["roi_unid_por_aposta"], g["jogos"])
        ev_mean = safe_weighted_mean(g["value_estimado"], g["jogos"])
        brier_proxy = float(
            (pd.to_numeric(g["hit_rate"], errors="coerce") - pd.to_numeric(g["form_recent_5"], errors="coerce"))
            .pow(2)
            .mean(skipna=True)
        ) if ("hit_rate" in g.columns and "form_recent_5" in g.columns) else None

        drawdown_proxy = None
        if roi_mean is not None:
            drawdown_proxy = max(0.0, min(1.0, -roi_mean * 3.0))

        out.append(
            {
                "league": str(league),
                "group": str(group),
                "markets": int(g.shape[0]),
                "bets": bets,
                "hit_rate": hit_rate,
                "roi_mean": roi_mean,
                "ev_mean": ev_mean,
                "drawdown_proxy": drawdown_proxy,
                "brier_proxy": brier_proxy if pd.notna(brier_proxy) else None,
            }
        )
    return out


def build_data_quality(
    base: Path,
    resumo: pd.DataFrame,
    mercados: pd.DataFrame,
    lay: pd.DataFrame,
    serie: pd.DataFrame,
) -> dict:
    checks: list[dict] = []

    checks.append(
        {
            "name": "Row count mínimo",
            "status": "ok" if all(x.shape[0] > 0 for x in (resumo, mercados, lay, serie)) else "warn",
            "detail": f"resumo={resumo.shape[0]}, mercados={mercados.shape[0]}, lay={lay.shape[0]}, serie={serie.shape[0]}",
        }
    )

    dup_cols = [c for c in ["league", "team", "scope", "market"] if c in mercados.columns]
    dup_count = int(mercados.duplicated(subset=dup_cols).sum()) if dup_cols else 0
    checks.append(
        {
            "name": "Duplicados mercado (league/team/scope/market)",
            "status": "ok" if dup_count == 0 else "warn",
            "detail": str(dup_count),
        }
    )

    missing_cols = [c for c in ["league", "team", "scope", "market", "jogos", "hit_rate"] if c in mercados.columns]
    missing_rate = float(mercados[missing_cols].isna().mean().mean()) if missing_cols else 0.0
    checks.append(
        {
            "name": "Missing rate campos chave",
            "status": "ok" if missing_rate <= 0.03 else "warn",
            "detail": f"{missing_rate * 100:.2f}%",
        }
    )

    hit = pd.to_numeric(mercados.get("hit_rate"), errors="coerce")
    bad_hit = int(((hit < 0) | (hit > 1)).sum()) if hit is not None else 0
    odds = pd.to_numeric(mercados.get("odds_avg"), errors="coerce")
    bad_odds = int((odds <= 1).sum()) if odds is not None else 0
    jogos = pd.to_numeric(mercados.get("jogos"), errors="coerce")
    bad_jogos = int((jogos <= 0).sum()) if jogos is not None else 0
    checks.append(
        {
            "name": "Outliers (hit/odds/jogos)",
            "status": "ok" if (bad_hit + bad_odds + bad_jogos) == 0 else "warn",
            "detail": f"hit={bad_hit}, odds={bad_odds}, jogos={bad_jogos}",
        }
    )

    source_files = sorted(base.glob("*.csv"))
    stale_days = None
    if source_files:
        newest = max(f.stat().st_mtime for f in source_files)
        stale_days = (datetime.now().timestamp() - newest) / 86400
    checks.append(
        {
            "name": "Staleness fontes CSV",
            "status": "ok" if stale_days is not None and stale_days <= 10 else "warn",
            "detail": "n/a" if stale_days is None else f"{stale_days:.1f} dias",
        }
    )

    return {
        "checks": checks,
        "summary": {
            "checks_total": len(checks),
            "checks_warn": sum(1 for c in checks if c["status"] != "ok"),
        },
    }


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    out = base / "output"
    site_data_path = base / "site" / "data" / "site-data.json"
    changelog_path = base / "site" / "data" / "changelog.json"
    site_data_path.parent.mkdir(parents=True, exist_ok=True)

    resumo = pd.read_csv(out / "resumo_equipas.csv")
    mercados = pd.read_csv(out / "mercados_equipas.csv")
    lay = pd.read_csv(out / "lay_top_por_equipa.csv")
    serie = pd.read_csv(out / "serie_temporal_equipas.csv")

    for df in (resumo, mercados, lay, serie):
        if "league" in df.columns:
            df["league"] = df["league"].astype(str)

    res_total = resumo[resumo["scope"] == "Total"].copy()
    res_total = res_total.sort_values(
        ["league", "ppg", "diff_golos"],
        ascending=[True, False, False],
    )

    league_overview: list[dict] = []
    rankings: dict[str, list[dict]] = {}
    for league, group in res_total.groupby("league"):
        group = group.sort_values(
            ["ppg", "diff_golos", "golos_marcados"],
            ascending=[False, False, False],
        )
        top = group.iloc[0]
        league_overview.append(
            {
                "league": league,
                "teams": int(group.shape[0]),
                "matches": int(round(group["jogos"].sum() / 2)),
                "topTeam": str(top["team"]),
                "topPPG": float(top["ppg"]),
                "avgGoals": float(group["golos_marcados"].mean()),
            }
        )
        rankings[league] = [
            {
                "team": str(r["team"]),
                "games": int(r["jogos"]),
                "ppg": float(r["ppg"]),
                "wins": float(r["vit%"]),
                "draws": float(r["emp%"]),
                "losses": float(r["der%"]),
                "gf": float(r["golos_marcados"]),
                "ga": float(r["golos_sofridos"]),
                "gd": float(r["diff_golos"]),
                "btts": float(r["BTTS%"]),
                "over25": float(r["O2.5%"]),
                "cs": float(r["CS%"]),
            }
            for _, r in group.iterrows()
        ]

    resumo_cols = [
        "league",
        "team",
        "scope",
        "jogos",
        "ppg",
        "vit%",
        "emp%",
        "der%",
        "golos_marcados",
        "golos_sofridos",
        "diff_golos",
        "marca%",
        "CS%",
        "BTTS%",
        "O2.5%",
        "U2.5%",
        "remates",
        "remates_sofridos",
        "SOT",
        "SOT_sofridos",
        "cantos",
        "cantos_sofridos",
        "amarelos",
        "amarelos_sofridos",
        "conversion_rate",
        "sot_pct",
    ]
    resumo_rows = resumo[[c for c in resumo_cols if c in resumo.columns]].copy()

    market_cols = [
        "league",
        "team",
        "scope",
        "market",
        "jogos",
        "hit_rate",
        "wilson_lo",
        "wilson_hi",
        "edge_vs_liga",
        "roi_unid_por_aposta",
        "odds_avg",
        "value_estimado",
        "form_recent_5",
    ]
    market_rows = mercados[[c for c in market_cols if c in mercados.columns]].copy()
    for c in (
        "hit_rate",
        "wilson_lo",
        "wilson_hi",
        "edge_vs_liga",
        "roi_unid_por_aposta",
        "odds_avg",
        "value_estimado",
        "form_recent_5",
    ):
        if c in market_rows.columns:
            market_rows[c] = pd.to_numeric(market_rows[c], errors="coerce")

    lay_cols = [
        "league",
        "team",
        "scope",
        "cenario_lay",
        "descricao",
        "jogos",
        "hit_rate",
        "lay_score",
        "flag_candidato",
    ]
    lay_rows = lay[[c for c in lay_cols if c in lay.columns]].copy()
    for c in ("hit_rate", "lay_score"):
        if c in lay_rows.columns:
            lay_rows[c] = pd.to_numeric(lay_rows[c], errors="coerce")
    if "flag_candidato" in lay_rows.columns:
        lay_rows["flag_candidato"] = (
            lay_rows["flag_candidato"].astype(str).str.lower().isin(["true", "1"])
        )

    serie["date"] = pd.to_datetime(serie["date"], errors="coerce")
    serie = serie.sort_values(["league", "team", "date"])
    serie_last = serie.groupby(["league", "team", "venue"], group_keys=False).tail(14).copy()
    serie_cols = [
        "league",
        "team",
        "venue",
        "date",
        "opponent",
        "gf",
        "ga",
        "points",
        "roll5_points",
        "roll5_gf",
        "roll5_ga",
        "roll5_goal_diff",
        "roll5_over_2_5",
        "roll5_btts",
        "roll5_clean_sheet",
    ]
    serie_rows = serie_last[[c for c in serie_cols if c in serie_last.columns]].copy()
    serie_rows["date"] = serie_rows["date"].dt.strftime("%Y-%m-%d")

    backtest_rows = build_backtest_rows(market_rows)
    data_quality = build_data_quality(base, resumo, mercados, lay, serie)

    changelog = []
    if changelog_path.exists():
        try:
            changelog = json.loads(changelog_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            changelog = []

    payload = {
        "meta": {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "sourceFiles": sorted([p.name for p in base.glob("*.csv")]),
            "generatedFrom": [
                "output/resumo_equipas.csv",
                "output/mercados_equipas.csv",
                "output/lay_top_por_equipa.csv",
                "output/serie_temporal_equipas.csv",
            ],
        },
        "overview": sorted(league_overview, key=lambda x: x["league"]),
        "rankings": rankings,
        "resumoRows": records(resumo_rows),
        "marketRows": records(market_rows),
        "layRows": records(lay_rows),
        "seriesRows": records(serie_rows),
        "backtestRows": backtest_rows,
        "dataQuality": data_quality,
        "changelog": changelog,
    }

    site_data_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(site_data_path)


if __name__ == "__main__":
    main()
