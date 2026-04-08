#!/usr/bin/env python3
"""
Builds site/data/site-data.json from analyzer outputs in ./output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def records(df: pd.DataFrame) -> list[dict]:
    # pandas -> json to guarantee NaN/Inf become null
    return json.loads(df.to_json(orient="records", force_ascii=False))


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    out = base / "output"
    site_data_path = base / "site" / "data" / "site-data.json"
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

    payload = {
        "meta": {
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
    }

    site_data_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(site_data_path)


if __name__ == "__main__":
    main()
