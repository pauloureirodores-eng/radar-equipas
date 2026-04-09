#!/usr/bin/env python3
"""
Builds site/data/site-data.json from analyzer outputs in ./output.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import numpy as np


def records(df: pd.DataFrame) -> list[dict]:
    # pandas -> json to guarantee NaN/Inf become null
    return json.loads(df.to_json(orient="records", force_ascii=False))


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


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
        merged["avg_games"] = pd.concat(
            [
                pd.to_numeric(merged["jogos_h"], errors="coerce"),
                pd.to_numeric(merged["jogos_a"], errors="coerce"),
            ],
            axis=1,
        ).mean(axis=1, skipna=True)
        merged["avg_ci_width"] = pd.concat(
            [
                pd.to_numeric(merged["wilson_hi_h"], errors="coerce") - pd.to_numeric(merged["wilson_lo_h"], errors="coerce"),
                pd.to_numeric(merged["wilson_hi_a"], errors="coerce") - pd.to_numeric(merged["wilson_lo_a"], errors="coerce"),
            ],
            axis=1,
        ).mean(axis=1, skipna=True)
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
        avg_games = float(pick["avg_games"]) if pd.notna(pick["avg_games"]) else 0.0
        ci_width = float(pick["avg_ci_width"]) if pd.notna(pick["avg_ci_width"]) else 0.35
        sample_factor = clamp(avg_games / 20.0, 0.0, 1.0)
        stability_factor = clamp(1.0 - (ci_width / 0.6), 0.0, 1.0)
        edge = float(pick["avg_edge"])
        edge_factor = clamp(edge / 0.12, 0.0, 1.0)
        confidence_score = int(round((0.45 * sample_factor + 0.35 * stability_factor + 0.20 * edge_factor) * 100.0))
        profit = (odds - 1.0) if hit else -1.0
        bets.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "league": league,
                "home": home,
                "away": away,
                "market": market,
                "odds": odds,
                "edge": edge,
                "sample_games": avg_games,
                "ci_width": ci_width,
                "confidence_score": confidence_score,
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
        "curve": records(curve_df[["date", "league", "home", "away", "market", "odds", "edge", "sample_games", "ci_width", "confidence_score", "hit", "profit", "capital", "drawdown"]]),
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


def build_phase2_calibration(phase2_model_rows: list[dict]) -> dict:
    if not phase2_model_rows:
        return {
            "summary": {
                "rows": 0,
                "weighted_samples": 0,
                "brier": None,
                "logloss": None,
                "ece": None,
            },
            "bins": [],
            "by_group": [],
        }

    df = pd.DataFrame(phase2_model_rows).copy()
    for col in ("sample_games", "p_model", "p_empirical"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["sample_games", "p_model", "p_empirical"])
    df = df[df["sample_games"] > 0]
    if df.empty:
        return {
            "summary": {
                "rows": 0,
                "weighted_samples": 0,
                "brier": None,
                "logloss": None,
                "ece": None,
            },
            "bins": [],
            "by_group": [],
        }

    # Weighted metrics with aggregated market-level targets.
    w = df["sample_games"].astype(float)
    p = df["p_model"].clip(1e-6, 1 - 1e-6)
    y = df["p_empirical"].clip(0, 1)
    brier = float((((p - y) ** 2) * w).sum() / w.sum())
    logloss = float(((-y * p.map(np.log) - (1 - y) * (1 - p).map(np.log)) * w).sum() / w.sum())

    # Reliability bins.
    edges = [i / 10 for i in range(11)]
    bins_out: list[dict] = []
    ece_num = 0.0
    for i in range(10):
        lo = edges[i]
        hi = edges[i + 1]
        if i < 9:
            bdf = df[(df["p_model"] >= lo) & (df["p_model"] < hi)]
        else:
            bdf = df[(df["p_model"] >= lo) & (df["p_model"] <= hi)]
        if bdf.empty:
            continue
        bw = bdf["sample_games"].astype(float)
        pred = float((bdf["p_model"] * bw).sum() / bw.sum())
        obs = float((bdf["p_empirical"] * bw).sum() / bw.sum())
        count = int(bdf.shape[0])
        weight = float(bw.sum())
        gap = abs(pred - obs)
        ece_num += gap * weight
        bins_out.append(
            {
                "bin": f"{int(lo * 100)}-{int(hi * 100)}%",
                "p_pred": pred,
                "p_obs": obs,
                "gap_abs": gap,
                "rows": count,
                "samples": weight,
            }
        )
    ece = float(ece_num / w.sum()) if w.sum() > 0 else None

    by_group_out: list[dict] = []
    for group, g in df.groupby("group"):
        gw = g["sample_games"].astype(float)
        gp = g["p_model"].clip(1e-6, 1 - 1e-6)
        gy = g["p_empirical"].clip(0, 1)
        gbrier = float((((gp - gy) ** 2) * gw).sum() / gw.sum())
        glogloss = float(((-gy * gp.map(np.log) - (1 - gy) * (1 - gp).map(np.log)) * gw).sum() / gw.sum())
        by_group_out.append(
            {
                "group": str(group),
                "rows": int(g.shape[0]),
                "samples": float(gw.sum()),
                "brier": gbrier,
                "logloss": glogloss,
                "avg_confidence": float((g["confidence_score"] * gw).sum() / gw.sum()) if "confidence_score" in g.columns else None,
            }
        )

    return {
        "summary": {
            "rows": int(df.shape[0]),
            "weighted_samples": float(w.sum()),
            "brier": brier,
            "logloss": logloss,
            "ece": ece,
        },
        "bins": bins_out,
        "by_group": by_group_out,
    }


def build_phase23_staking(temporal_backtest: dict) -> dict:
    curve = temporal_backtest.get("curve", []) or []
    if not curve:
        return {
            "strategies": [],
            "curve": [],
            "weekly": [],
            "best_strategy": None,
        }

    df = pd.DataFrame(curve).copy()
    for c in ("odds", "edge", "confidence_score"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["odds"] = df["odds"].fillna(2.0).clip(lower=1.01)
    df["edge"] = df["edge"].fillna(0.0)
    df["confidence_score"] = df["confidence_score"].fillna(50.0).clip(lower=0, upper=100)

    # Approximate model probability from odds implied + measured edge.
    df["p_model"] = (1.0 / df["odds"] + df["edge"]).clip(lower=0.02, upper=0.98)
    df["hit01"] = df["hit"].astype(bool).astype(int)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")

    def stake_flat(_row: pd.Series) -> float:
        return 1.0

    def stake_kelly_quarter(row: pd.Series) -> float:
        odds = float(row["odds"])
        p = float(row["p_model"])
        kelly = max(0.0, (p * odds - 1.0) / (odds - 1.0))
        # Fractional Kelly with stricter cap to control compounding volatility.
        return float(clamp(kelly * 0.25, 0.0, 0.008))

    def stake_dynamic_conservative(row: pd.Series) -> float:
        conf = float(row["confidence_score"]) / 100.0
        edge = clamp(float(row["edge"]) / 0.10, 0.0, 1.0)
        raw = 0.002 + 0.004 * conf + 0.004 * edge
        return float(clamp(raw, 0.0015, 0.01))

    strategy_defs = [
        ("flat_1u", "Flat stake (1u)", stake_flat, 100.0, "units"),
        ("kelly_q", "Kelly 0.25 (cap 0.8%)", stake_kelly_quarter, 100.0, "bankroll_pct"),
        ("dynamic_c", "Dinâmica conservadora (0.15%-1.0%)", stake_dynamic_conservative, 100.0, "bankroll_pct"),
    ]

    curve_rows: list[dict] = []
    summaries: list[dict] = []
    weekly_rows: list[dict] = []

    for key, label, stake_fn, initial_capital, stake_type in strategy_defs:
        cap = float(initial_capital)
        peak = cap
        invested = 0.0
        wins = 0
        strat_curve: list[dict] = []
        for _, row in df.iterrows():
            if stake_type == "units":
                stake = float(stake_fn(row))
            else:
                stake_pct = float(stake_fn(row))
                stake = cap * stake_pct
            stake = max(0.0, stake)
            odds = float(row["odds"])
            is_hit = bool(row["hit"])
            profit = stake * (odds - 1.0) if is_hit else -stake
            cap += profit
            peak = max(peak, cap)
            dd_abs = max(0.0, peak - cap)
            dd_pct = (dd_abs / peak) if peak > 0 else 0.0
            invested += stake
            wins += 1 if is_hit else 0
            strat_curve.append(
                {
                    "strategy": key,
                    "strategy_label": label,
                    "date": row["date"].strftime("%Y-%m-%d"),
                    "stake": float(stake),
                    "stake_pct": float(stake / cap) if cap > 0 else None,
                    "profit": float(profit),
                    "capital": float(cap),
                    "drawdown_abs": float(dd_abs),
                    "drawdown_pct": float(dd_pct),
                    "hit": bool(is_hit),
                }
            )

        sdf = pd.DataFrame(strat_curve)
        curve_rows.extend(strat_curve)

        iso = pd.to_datetime(sdf["date"]).dt.isocalendar()
        sdf["week_key"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
        wdf = (
            sdf.groupby("week_key", as_index=False)
            .agg(
                bets=("profit", "count"),
                wins=("hit", "sum"),
                stake_total=("stake", "sum"),
                profit=("profit", "sum"),
                capital_end=("capital", "last"),
                max_drawdown_abs=("drawdown_abs", "max"),
                max_drawdown_pct=("drawdown_pct", "max"),
            )
            .sort_values("week_key")
        )
        wdf["hit_rate"] = wdf["wins"] / wdf["bets"]
        wdf["roi"] = wdf["profit"] / wdf["stake_total"]
        wdf["strategy"] = key
        wdf["strategy_label"] = label
        weekly_rows.extend(records(wdf))

        total_bets = int(sdf.shape[0])
        summaries.append(
            {
                "strategy": key,
                "strategy_label": label,
                "initial_capital": float(initial_capital),
                "final_capital": float(cap),
                "total_profit": float(cap - initial_capital),
                "total_bets": total_bets,
                "wins": int(wins),
                "hit_rate": float(wins / total_bets) if total_bets else None,
                "total_staked": float(invested),
                "roi_on_staked": float((cap - initial_capital) / invested) if invested > 0 else None,
                "max_drawdown_abs": float(sdf["drawdown_abs"].max()) if not sdf.empty else 0.0,
                "max_drawdown_pct": float(sdf["drawdown_pct"].max()) if not sdf.empty else 0.0,
            }
        )

    best = None
    if summaries:
        best = sorted(
            summaries,
            key=lambda x: (
                (x.get("roi_on_staked") if x.get("roi_on_staked") is not None else -999),
                -(x.get("max_drawdown_pct") if x.get("max_drawdown_pct") is not None else 999),
            ),
            reverse=True,
        )[0]["strategy"]

    return {
        "strategies": summaries,
        "curve": curve_rows,
        "weekly": weekly_rows,
        "best_strategy": best,
    }


def build_phase24_profiles(phase23_staking: dict) -> dict:
    strategies = phase23_staking.get("strategies", []) or []
    weekly = phase23_staking.get("weekly", []) or []
    if not strategies:
        return {"profiles": []}

    wdf = pd.DataFrame(weekly) if weekly else pd.DataFrame(columns=["strategy", "roi"])
    if not wdf.empty and "roi" in wdf.columns:
        wdf["roi"] = pd.to_numeric(wdf["roi"], errors="coerce")

    def norm(v: float | None, lo: float, hi: float) -> float:
        if v is None or not np.isfinite(v) or hi <= lo:
            return 0.0
        return float(clamp((v - lo) / (hi - lo), 0.0, 1.0))

    enriched: list[dict] = []
    for s in strategies:
        sid = str(s.get("strategy"))
        if not wdf.empty and "strategy" in wdf.columns:
            w = wdf[wdf["strategy"] == sid]
        else:
            w = pd.DataFrame()
        weekly_roi_std = float(w["roi"].std(skipna=True)) if (not w.empty and "roi" in w.columns) else None
        initial_cap = float(s.get("initial_capital") or 100.0)
        final_cap = float(s.get("final_capital") or initial_cap)
        profit_pct = (final_cap - initial_cap) / initial_cap if initial_cap > 0 else None
        enriched.append(
            {
                **s,
                "profit_pct": profit_pct,
                "weekly_roi_std": weekly_roi_std,
            }
        )

    profile_defs = [
        {
            "id": "conservador",
            "label": "Conservador",
            "weights": {"dd": 0.50, "stability": 0.25, "roi": 0.15, "profit": 0.10},
        },
        {
            "id": "balanceado",
            "label": "Balanceado",
            "weights": {"dd": 0.35, "stability": 0.20, "roi": 0.30, "profit": 0.15},
        },
        {
            "id": "agressivo",
            "label": "Agressivo",
            "weights": {"dd": 0.15, "stability": 0.10, "roi": 0.45, "profit": 0.30},
        },
    ]

    profiles: list[dict] = []
    for p in profile_defs:
        ranking: list[dict] = []
        for s in enriched:
            dd = float(s.get("max_drawdown_pct") or 0.0)
            roi = float(s.get("roi_on_staked") or 0.0)
            profit_pct = float(s.get("profit_pct") or 0.0)
            weekly_std = s.get("weekly_roi_std")

            dd_score = norm(1.0 - dd, 0.60, 1.0)
            stability_score = norm(0.25 - (weekly_std if weekly_std is not None else 0.25), 0.0, 0.25)
            roi_score = norm(roi, -0.05, 0.35)
            profit_score = norm(profit_pct, -0.20, 2.50)

            score = (
                p["weights"]["dd"] * dd_score
                + p["weights"]["stability"] * stability_score
                + p["weights"]["roi"] * roi_score
                + p["weights"]["profit"] * profit_score
            ) * 100.0

            ranking.append(
                {
                    "strategy": s.get("strategy"),
                    "strategy_label": s.get("strategy_label"),
                    "score": float(score),
                    "max_drawdown_pct": dd,
                    "roi_on_staked": roi,
                    "profit_pct": profit_pct,
                    "weekly_roi_std": weekly_std,
                    "hit_rate": s.get("hit_rate"),
                    "total_bets": s.get("total_bets"),
                    "final_capital": s.get("final_capital"),
                }
            )

        ranking = sorted(ranking, key=lambda x: x["score"], reverse=True)
        best = ranking[0] if ranking else None
        profiles.append(
            {
                "id": p["id"],
                "label": p["label"],
                "recommendation": best,
                "ranking": ranking,
            }
        )

    return {"profiles": profiles}


def build_weekly_alerts(serie_full: pd.DataFrame, market_rows: pd.DataFrame) -> dict:
    alerts: list[dict] = []

    # Team form alerts from temporal series.
    s = serie_full.copy()
    s["date"] = pd.to_datetime(s["date"], errors="coerce")
    s = s.dropna(subset=["date"]).sort_values(["league", "team", "date"])
    for (league, team), g in s.groupby(["league", "team"], dropna=False):
        vals = pd.to_numeric(g.get("roll5_points"), errors="coerce").dropna()
        if vals.shape[0] < 2:
            continue
        delta = float(vals.iloc[-1] - vals.iloc[-2])
        abs_delta = abs(delta)
        if abs_delta < 0.45:
            continue
        severity = "high" if abs_delta >= 0.9 else "medium"
        direction = "up" if delta > 0 else "down"
        alerts.append(
            {
                "league": str(league),
                "type": "team_form",
                "entity": str(team),
                "market": None,
                "direction": direction,
                "severity": severity,
                "score": float(abs_delta * 100.0),
                "delta": delta,
                "message": f"{team}: forma em pontos {'subiu' if delta > 0 else 'caiu'} {delta:+.2f} (ultimo vs anterior).",
            }
        )

    # Market alerts from recent form vs season baseline.
    m = market_rows.copy()
    for col in ("jogos", "hit_rate", "form_recent_5"):
        if col in m.columns:
            m[col] = pd.to_numeric(m[col], errors="coerce")
    m = m[(m["scope"] == "Total") & (m["jogos"] >= 8)]
    m["delta"] = m["form_recent_5"] - m["hit_rate"]
    m = m[m["delta"].notna() & (m["delta"].abs() >= 0.12)]
    for _, r in m.iterrows():
        delta = float(r["delta"])
        abs_delta = abs(delta)
        severity = "high" if abs_delta >= 0.20 else "medium"
        direction = "up" if delta > 0 else "down"
        alerts.append(
            {
                "league": str(r["league"]),
                "type": "market_shift",
                "entity": str(r["team"]),
                "market": str(r["market"]),
                "direction": direction,
                "severity": severity,
                "score": float(abs_delta * 100.0),
                "delta": delta,
                "message": f"{r['team']} - {r['market']}: forma 5J {'acima' if delta > 0 else 'abaixo'} da epoca ({delta * 100:+.1f} pp).",
            }
        )

    alerts = sorted(
        alerts,
        key=lambda x: (
            1 if x["severity"] == "high" else 0,
            x["score"],
        ),
        reverse=True,
    )
    by_league: dict[str, list[dict]] = {}
    for a in alerts:
        lg = a["league"]
        by_league.setdefault(lg, []).append(a)
    for lg in list(by_league.keys()):
        by_league[lg] = by_league[lg][:30]

    return {
        "summary": {
            "total": int(len(alerts)),
            "high": int(sum(1 for a in alerts if a["severity"] == "high")),
            "medium": int(sum(1 for a in alerts if a["severity"] == "medium")),
        },
        "global": alerts[:120],
        "byLeague": by_league,
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
    phase2_calibration = build_phase2_calibration(phase2_model_rows)
    phase23_staking = build_phase23_staking(temporal_backtest)
    phase24_profiles = build_phase24_profiles(phase23_staking)
    weekly_alerts = build_weekly_alerts(serie_full, market_rows)

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
        "phase2Calibration": phase2_calibration,
        "phase23Staking": phase23_staking,
        "phase24Profiles": phase24_profiles,
        "weeklyAlerts": weekly_alerts,
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
