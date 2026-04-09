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


def eval_market_hit(market: str, gf: float, ga: float) -> bool | None:
    m = str(market or "").lower()
    total = gf + ga
    if "over 2.5" in m:
        return total >= 3
    if "under 2.5" in m:
        return total <= 2
    if "ambas marcam" in m or "btts" in m:
        return gf > 0 and ga > 0
    if "clean sheet" in m:
        return ga == 0
    if "casa marca" in m:
        return gf >= 1
    return None


def build_temporal_backtest(
    market_rows: pd.DataFrame,
    serie_full: pd.DataFrame,
) -> dict:
    home_matches = serie_full[serie_full["venue"] == "H"].copy()
    home_matches["date"] = pd.to_datetime(home_matches["date"], errors="coerce")
    home_matches = home_matches.dropna(subset=["date"]).sort_values("date")

    supported_markets = [
        "Over 2.5 golos",
        "Under 2.5 golos",
        "Ambas marcam (BTTS)",
        "Casa marca (>=1)",
        "Clean sheet",
    ]
    mdf = market_rows[market_rows["market"].isin(supported_markets)].copy()

    bets: list[dict] = []
    for _, r in home_matches.iterrows():
        league = str(r["league"])
        home = str(r["team"])
        away = str(r.get("opponent", ""))
        gf = float(r.get("gf", 0))
        ga = float(r.get("ga", 0))
        dt = pd.to_datetime(r["date"], errors="coerce")
        if pd.isna(dt):
            continue

        hm = mdf[(mdf["league"] == league) & (mdf["team"] == home) & (mdf["scope"] == "Casa")]
        aw = mdf[(mdf["league"] == league) & (mdf["team"] == away) & (mdf["scope"] == "Fora")]
        if hm.empty or aw.empty:
            continue

        merged = hm.merge(
            aw,
            on="market",
            suffixes=("_h", "_a"),
            how="inner",
        )
        if merged.empty:
            continue

        merged["avg_edge"] = pd.to_numeric(merged["edge_vs_liga_h"], errors="coerce").add(
            pd.to_numeric(merged["edge_vs_liga_a"], errors="coerce"),
            fill_value=0.0,
        ) / 2.0
        merged["avg_odds"] = pd.concat(
            [
                pd.to_numeric(merged["odds_avg_h"], errors="coerce"),
                pd.to_numeric(merged["odds_avg_a"], errors="coerce"),
            ],
            axis=1,
        ).mean(axis=1, skipna=True)

        candidates = merged[
            (merged["avg_edge"] > 0)
            & (merged["avg_odds"] > 1.01)
        ].sort_values("avg_edge", ascending=False)
        if candidates.empty:
            continue

        pick = candidates.iloc[0]
        market = str(pick["market"])
        hit = eval_market_hit(market, gf, ga)
        if hit is None:
            continue
        odds = float(pick["avg_odds"])
        profit = (odds - 1.0) if hit else -1.0
        bets.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "league": league,
                "home": home,
                "away": away,
                "market": market,
                "odds": odds,
                "edge": float(pick["avg_edge"]),
                "hit": bool(hit),
                "profit": float(profit),
            }
        )

    if not bets:
        return {
            "initial_bankroll": 100.0,
            "final_bankroll": 100.0,
            "total_bets": 0,
            "hit_rate": None,
            "roi": None,
            "max_drawdown": 0.0,
            "curve": [],
            "weekly": [],
        }

    bankroll = 100.0
    peak = bankroll
    wins = 0
    curve: list[dict] = []
    for b in bets:
        bankroll += b["profit"]
        peak = max(peak, bankroll)
        drawdown = max(0.0, peak - bankroll)
        wins += 1 if b["hit"] else 0
        curve.append({**b, "capital": float(bankroll), "drawdown": float(drawdown)})

    curve_df = pd.DataFrame(curve)
    dt = pd.to_datetime(curve_df["date"], errors="coerce")
    iso = dt.dt.isocalendar()
    curve_df["week_key"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    weekly_df = (
        curve_df.groupby("week_key", as_index=False)
        .agg(
            bets=("profit", "count"),
            wins=("hit", "sum"),
            profit=("profit", "sum"),
            capital_end=("capital", "last"),
            max_drawdown_week=("drawdown", "max"),
        )
        .sort_values("week_key")
    )
    weekly_df["hit_rate"] = weekly_df["wins"] / weekly_df["bets"]
    weekly_df["roi"] = weekly_df["profit"] / weekly_df["bets"]

    return {
        "initial_bankroll": 100.0,
        "final_bankroll": float(bankroll),
        "total_bets": int(len(curve)),
        "hit_rate": float(wins / len(curve)),
        "roi": float(curve_df["profit"].sum() / len(curve)),
        "max_drawdown": float(curve_df["drawdown"].max()),
        "curve": records(curve_df[["date", "league", "home", "away", "market", "odds", "edge", "hit", "profit", "capital", "drawdown"]]),
        "weekly": records(weekly_df[["week_key", "bets", "wins", "hit_rate", "roi", "profit", "capital_end", "max_drawdown_week"]]),
    }


def build_phase2_sos(resumo: pd.DataFrame, serie_full: pd.DataFrame) -> list[dict]:
    res_total = resumo[resumo["scope"] == "Total"].copy()
    ppg_map = {
        (str(r["league"]), str(r["team"])): float(r["ppg"])
        for _, r in res_total.iterrows()
        if pd.notna(r.get("ppg"))
    }
    league_avg_ppg = (
        res_total.groupby("league")["ppg"].mean().to_dict()
        if "ppg" in res_total.columns
        else {}
    )

    out: list[dict] = []
    for (league, team), g in serie_full.groupby(["league", "team"]):
        opp_ppg = []
        for opp in g.get("opponent", pd.Series(dtype=str)).astype(str):
            key = (str(league), str(opp))
            if key in ppg_map:
                opp_ppg.append(ppg_map[key])
        if not opp_ppg:
            continue

        points = pd.to_numeric(g.get("points"), errors="coerce")
        raw_ppg = float(points.mean()) if points.notna().any() else None
        if raw_ppg is None:
            continue

        sos = float(sum(opp_ppg) / len(opp_ppg))
        lg_avg = float(league_avg_ppg.get(league, raw_ppg))
        adj_ppg = raw_ppg * (sos / lg_avg) if lg_avg > 0 else raw_ppg

        last5 = points.dropna().tail(5)
        last5_ppg = float(last5.mean()) if not last5.empty else None
        out.append(
            {
                "league": str(league),
                "team": str(team),
                "raw_ppg": raw_ppg,
                "sos_ppg": sos,
                "adj_ppg": adj_ppg,
                "last5_ppg": last5_ppg,
                "sample_matches": int(points.dropna().shape[0]),
            }
        )
    return out


def build_phase2_model_rows(market_rows: pd.DataFrame) -> list[dict]:
    df = market_rows.copy()
    num_cols = [
        "jogos",
        "hit_rate",
        "wilson_lo",
        "wilson_hi",
        "odds_avg",
        "value_estimado",
        "form_recent_5",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    for required in ("league", "team", "scope", "market"):
        if required not in df.columns:
            return []

    league_market_prior = (
        df.groupby(["league", "scope", "market"], dropna=False)["hit_rate"]
        .mean()
        .to_dict()
    )
    global_market_prior = df.groupby("market", dropna=False)["hit_rate"].mean().to_dict()
    global_prior = float(df["hit_rate"].mean()) if df["hit_rate"].notna().any() else 0.5
    prior_strength = 10.0

    out: list[dict] = []
    for _, r in df.iterrows():
        league = str(r["league"])
        team = str(r["team"])
        scope = str(r["scope"])
        market = str(r["market"])

        n = float(r.get("jogos") or 0.0)
        hit = r.get("hit_rate")
        if not pd.notna(hit):
            continue
        p_emp = float(hit)
        if p_emp < 0 or p_emp > 1:
            continue

        prior = league_market_prior.get((league, scope, market))
        if prior is None or not pd.notna(prior):
            prior = global_market_prior.get(market, global_prior)
        prior = float(prior) if pd.notna(prior) else global_prior
        prior = max(0.02, min(0.98, prior))

        alpha0 = prior * prior_strength
        beta0 = (1.0 - prior) * prior_strength
        k = p_emp * max(n, 0.0)
        p_post = (k + alpha0) / (max(n, 0.0) + alpha0 + beta0)

        recent = r.get("form_recent_5")
        if pd.notna(recent):
            recent = max(0.0, min(1.0, float(recent)))
            w_recent = min(0.2, 0.2 * (10.0 / max(n, 10.0)))
            p_model = (1.0 - w_recent) * p_post + w_recent * recent
        else:
            p_model = p_post

        wilson_lo = r.get("wilson_lo")
        wilson_hi = r.get("wilson_hi")
        if pd.notna(wilson_lo) and pd.notna(wilson_hi):
            lo = float(wilson_lo)
            hi = float(wilson_hi)
        else:
            # Fallback CI approximation for Bernoulli proportion.
            sd = (p_model * (1.0 - p_model) / max(n, 1.0)) ** 0.5
            lo = max(0.0, p_model - 1.96 * sd)
            hi = min(1.0, p_model + 1.96 * sd)
        ci_width = max(0.0, hi - lo)

        odds = r.get("odds_avg")
        if pd.notna(odds) and float(odds) > 1.01:
            odds_v = float(odds)
            p_implied = 1.0 / odds_v
            edge_vs_odds = p_model - p_implied
            ev_model = p_model * odds_v - 1.0
            fair_odds = 1.0 / max(p_model, 1e-9)
        else:
            odds_v = None
            p_implied = None
            edge_vs_odds = None
            ev_model = None
            fair_odds = None

        sample_factor = max(0.0, min(1.0, n / 20.0))
        stability_factor = max(0.0, min(1.0, 1.0 - (ci_width / 0.6)))
        edge_factor = max(0.0, min(1.0, abs(edge_vs_odds) / 0.12)) if edge_vs_odds is not None else 0.0
        confidence_score = round((0.45 * sample_factor + 0.35 * stability_factor + 0.20 * edge_factor) * 100.0)
        if n < 8:
            sample_quality = "baixa"
        elif n < 16:
            sample_quality = "média"
        else:
            sample_quality = "alta"

        out.append(
            {
                "league": league,
                "team": team,
                "scope": scope,
                "market": market,
                "group": market_group(market),
                "sample_games": int(round(n)),
                "sample_quality": sample_quality,
                "p_empirical": p_emp,
                "p_prior": prior,
                "p_model": float(p_model),
                "p_implied_odds": p_implied,
                "fair_odds": fair_odds,
                "odds_avg": odds_v,
                "ev_model": ev_model,
                "edge_vs_odds": edge_vs_odds,
                "ci_lo": lo,
                "ci_hi": hi,
                "ci_width": ci_width,
                "confidence_score": int(confidence_score),
            }
        )

    return out


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
    serie_full = serie.copy()
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
    temporal_backtest = build_temporal_backtest(market_rows, serie_full)
    phase2_sos = build_phase2_sos(resumo, serie_full)
    phase2_model_rows = build_phase2_model_rows(market_rows)

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
        "temporalBacktest": temporal_backtest,
        "phase2Sos": phase2_sos,
        "phase2ModelRows": phase2_model_rows,
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
