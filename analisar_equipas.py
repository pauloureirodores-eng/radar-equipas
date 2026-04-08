#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analisador de equipas (futebol) a partir de CSVs (formato típico football-data.co.uk).
Pode ler um CSV único ou concatenar automaticamente todos os CSVs numa pasta (recomendado para várias ligas).

O que faz:
- Lê o CSV
- Detecta a liga (coluna Div) -> coluna normalizada "league"
- Constrói um dataset "por equipa por jogo" (casa/fora)
- Calcula métricas de performance (pontos, golos, remates, cantos, disciplina, etc.)
- Calcula "mercados" com taxa de acerto e, quando existirem odds no CSV, ROI histórico
- Produz ficheiros de saída (CSV + Excel + relatórios Markdown por equipa)
- Série temporal com médias móveis

Saídas:
- Sempre: outputs combinados (todas as ligas) na pasta --outdir
- Se existirem várias ligas: também cria subpastas por liga (E0, E1, ...)

⚠️ Nota: análise histórica; não garante resultados futuros.
"""

from __future__ import annotations

import argparse
import re
import math
from pathlib import Path
from typing import Dict, Tuple, Optional, List

import numpy as np
import pandas as pd

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger(__name__)


# -----------------------------
# Utilitários (formatação)
# -----------------------------

def _pct(x: float) -> str:
    if pd.isna(x):
        return "—"
    return f"{100*x:.1f}%"


def _num(x: float) -> str:
    if pd.isna(x):
        return "—"
    return f"{x:.2f}"


def _roi(x: float) -> str:
    if pd.isna(x):
        return "—"
    return f"{x:+.3f}"


# -----------------------------
# Utilitários (cálculo estatístico)
# -----------------------------

def safe_div(num: float, den: float) -> float:
    if pd.isna(num) or pd.isna(den) or den == 0:
        return np.nan
    return float(num) / float(den)


def wilson_interval(k: float, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Intervalo de confiança de Wilson para uma proporção binária.

    - k: sucessos (pode ser float se vier de somas de booleanos; será arredondado para int)
    - n: amostra
    - z: 1.96 ~ 95%
    """
    if n <= 0 or pd.isna(k):
        return (np.nan, np.nan)
    k_i = int(round(float(k)))
    p = k_i / n
    denom = 1.0 + (z**2) / n
    centre = p + (z**2) / (2*n)
    adj = z * math.sqrt((p*(1-p) + (z**2)/(4*n)) / n)
    lo = (centre - adj) / denom
    hi = (centre + adj) / denom
    return (max(0.0, lo), min(1.0, hi))

# -----------------------------
# Leitura e preparação
# -----------------------------

def _read_csv_any(path: Path) -> pd.DataFrame:
    """Lê CSV com alguns 'failsafes' (encoding e separador)."""
    try:
        df = pd.read_csv(path)
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="latin-1")

    # Alguns ficheiros vêm com ';' como separador e acabam numa única coluna.
    if df.shape[1] == 1:
        try:
            df2 = pd.read_csv(path, sep=";")
            if df2.shape[1] > 1:
                df = df2
        except Exception:
            pass

    return df


def infer_league_from_filename(path: Path) -> str:
    """Inferir código de liga (Div) a partir do nome do ficheiro (ex.: E0.csv -> E0)."""
    stem = path.stem.strip()
    m = re.match(r"^([A-Za-z]{1,4}\d{0,2})", stem)
    return (m.group(1).upper() if m else stem.upper())


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza nomes de colunas mais comuns do football-data (HG/AG/Res -> FTHG/FTAG/FTR)."""
    # Resultados (aliases presentes na 'Key')
    if "FTHG" not in df.columns and "HG" in df.columns:
        df["FTHG"] = df["HG"]
    if "FTAG" not in df.columns and "AG" in df.columns:
        df["FTAG"] = df["AG"]
    if "FTR" not in df.columns and "Res" in df.columns:
        df["FTR"] = df["Res"]

    return df


def read_matches(csv_path: Path, *, default_league: Optional[str] = None, add_source: bool = True) -> pd.DataFrame:
    """Lê um CSV e devolve um DataFrame com coluna normalizada 'league'.

    - Se não existir 'Div'/'League', usa default_league (ou 'ALL').
    - Converte Date para datetime (dayfirst=True).
    - Adiciona 'source_file' para auditoria (opcional).
    """
    df = _read_csv_any(csv_path)
    df = normalise_columns(df)

    # Datas no formato dd/mm/aaaa (típico football-data.co.uk)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")

    # Liga/divisão
    if "league" not in df.columns:
        if "Div" in df.columns:
            df["league"] = df["Div"].astype(str)
        elif "League" in df.columns:
            df["league"] = df["League"].astype(str)
        else:
            df["league"] = (default_league or "ALL")

    if add_source and "source_file" not in df.columns:
        df["source_file"] = csv_path.name

    return df


def read_matches_from_dir(csv_dir: Path, *, pattern: str = "*.csv") -> pd.DataFrame:
    """Lê todos os CSVs numa pasta (não-recursivo) e concatena.

    Útil para evitar colagens manuais de ligas diferentes num único ficheiro.
    """
    csv_dir = Path(csv_dir)
    paths = sorted([p for p in csv_dir.glob(pattern) if p.is_file()])
    if not paths:
        raise FileNotFoundError(f"Não foram encontrados CSVs em: {csv_dir.resolve()} (pattern={pattern})")

    dfs: List[pd.DataFrame] = []
    for p in paths:
        lg = infer_league_from_filename(p)
        df = read_matches(p, default_league=lg, add_source=True)
        dfs.append(df)

    # sort=False preserva ordem de colunas; missing cols ficam NaN
    return pd.concat(dfs, ignore_index=True, sort=False)


# -----------------------------
# Temporadas / fases da época
# -----------------------------

def infer_season(dt: pd.Timestamp) -> Optional[str]:
    """Inferir a época no formato 'YYYY-YY' a partir da data.

    Heurística europeia comum: épocas começam em Julho (>=7).
    """
    if pd.isna(dt):
        return None
    y = int(dt.year)
    m = int(dt.month)
    start = y if m >= 7 else (y - 1)
    end = (start + 1) % 100
    return f"{start}-{end:02d}"


def add_season_phase(matches: pd.DataFrame, split: str = "none") -> pd.DataFrame:
    """Adiciona colunas 'season' e 'phase' (opcional) ao dataframe de jogos.

    split:
    - 'none'   -> apenas 'season'
    - 'halves' -> 1ª/2ª metade (por quantis de data dentro de liga+season)
    - 'thirds' -> terços (início/meio/fim)
    """
    m = matches.copy()
    if "Date" not in m.columns:
        m["season"] = None
        m["phase"] = None
        return m

    m["season"] = m["Date"].apply(infer_season)

    if split == "none":
        m["phase"] = None
        return m

    # Segmentação por quantis de data dentro de liga+season (robusto a calendários diferentes)
    key_cols = ["league", "season"] if "league" in m.columns else ["season"]
    m["phase"] = None

    if split == "halves":
        labels = ["1ª metade", "2ª metade"]
        q = [0.5]
    elif split == "thirds":
        labels = ["Início", "Meio", "Fim"]
        q = [1/3, 2/3]
    else:
        raise ValueError(f"--season-split inválido: {split}")

    for keys, g in m.groupby(key_cols, dropna=False):
        dates = g["Date"].dropna().sort_values()
        if dates.empty:
            continue
        cuts = [dates.quantile(p) for p in q]
        idx = g.index
        d = m.loc[idx, "Date"]
        if split == "halves":
            m.loc[idx, "phase"] = np.where(d <= cuts[0], labels[0], labels[1])
        else:
            m.loc[idx, "phase"] = np.select(
                [d <= cuts[0], d <= cuts[1]],
                [labels[0], labels[1]],
                default=labels[2],
            )

    return m

# -----------------------------
# Odds / lucros (1 unidade)
# -----------------------------

def profit_1x2(won: bool, odds: float) -> float:
    if pd.isna(odds):
        return np.nan
    return (odds - 1.0) if won else -1.0


def profit_ou(event: bool, odds: float) -> float:
    if pd.isna(odds):
        return np.nan
    return (odds - 1.0) if event else -1.0


def ah_profit(goal_diff: float, line: float, odds: float) -> float:
    """
    Handicap asiático (linha para a equipa analisada).
    - goal_diff = gf - ga
    - line = AH (ex.: -0.5, +0.25, etc.)
    Retorna lucro por 1 unidade (aproximação para meia vitória/derrota).
    """
    if pd.isna(line) or pd.isna(odds) or pd.isna(goal_diff):
        return np.nan

    margin = goal_diff + line

    # aproximação das linhas em quartos
    # margem >= 0.5 -> win
    # margem == 0 -> push
    # margem <= -0.5 -> loss
    # margem == +/-0.25 -> half win/loss
    if margin >= 0.5:
        return odds - 1.0
    eps = 1e-9

    if abs(margin) < eps:
        return 0.0
    if margin <= -0.5:
        return -1.0
    if abs(margin - 0.25) < eps:
        return (odds - 1.0) / 2.0
    if abs(margin + 0.25) < eps:
        return -0.5

    # fallback (casos raros)
    return np.nan


# -----------------------------
# Construção "team-games"
# -----------------------------

def build_team_games(matches: pd.DataFrame) -> pd.DataFrame:
    """
    Constrói um dataframe 'longo' com 2 linhas por jogo:
    - uma para a equipa da casa
    - outra para a equipa visitante
    """
    m = matches.copy()

    # Derivadas do jogo
    m["total_goals"] = m["FTHG"].fillna(0) + m["FTAG"].fillna(0)
    m["btts"] = (m["FTHG"] > 0) & (m["FTAG"] > 0)
    m["over_2_5"] = m["total_goals"] >= 3
    m["under_2_5"] = m["total_goals"] <= 2

    # Helper para aceder a colunas opcionais
    def col(name: str) -> pd.Series:
        return m[name] if name in m.columns else pd.Series([np.nan] * len(m), index=m.index)

    # Casa
    home = pd.DataFrame({
        "match_id": m.index,
        "league": m.get("league"),
        "date": m.get("Date"),
        "season": m.get("season") if "season" in m.columns else None,
        "phase": m.get("phase") if "phase" in m.columns else None,
        "team": m.get("HomeTeam"),
        "opponent": m.get("AwayTeam"),
        "venue": "H",
        "gf": m.get("FTHG"),
        "ga": m.get("FTAG"),
        "result": m.get("FTR").map({"H": "W", "D": "D", "A": "L"}),
        "points": m.get("FTR").map({"H": 3, "D": 1, "A": 0}),
        "total_goals": m["total_goals"],
        "btts": m["btts"],
        "over_2_5": m["over_2_5"],
        "under_2_5": m["under_2_5"],
        "team_scored": m.get("FTHG") > 0,
        "clean_sheet": m.get("FTAG") == 0,

        # estatísticas (se existirem)
        "shots_for": col("HS"),
        "shots_against": col("AS"),
        "sot_for": col("HST"),
        "sot_against": col("AST"),
        "corners_for": col("HC"),
        "corners_against": col("AC"),
        "yellows_for": col("HY"),
        "yellows_against": col("AY"),
        "reds_for": col("HR"),
        "reds_against": col("AR"),

        # odds médias (se existirem)
        "odds_win": col("AvgH"),
        "odds_over2_5": col("Avg>2.5"),
        "odds_under2_5": col("Avg<2.5"),
        "ah_line": col("AHh"),
        "odds_ah": col("AvgAHH"),
    })

    # Fora
    away = pd.DataFrame({
        "match_id": m.index,
        "league": m.get("league"),
        "date": m.get("Date"),
        "season": m.get("season") if "season" in m.columns else None,
        "phase": m.get("phase") if "phase" in m.columns else None,
        "team": m.get("AwayTeam"),
        "opponent": m.get("HomeTeam"),
        "venue": "A",
        "gf": m.get("FTAG"),
        "ga": m.get("FTHG"),
        "result": m.get("FTR").map({"H": "L", "D": "D", "A": "W"}),
        "points": m.get("FTR").map({"H": 0, "D": 1, "A": 3}),
        "total_goals": m["total_goals"],
        "btts": m["btts"],
        "over_2_5": m["over_2_5"],
        "under_2_5": m["under_2_5"],
        "team_scored": m.get("FTAG") > 0,
        "clean_sheet": m.get("FTHG") == 0,

        "shots_for": col("AS"),
        "shots_against": col("HS"),
        "sot_for": col("AST"),
        "sot_against": col("HST"),
        "corners_for": col("AC"),
        "corners_against": col("HC"),
        "yellows_for": col("AY"),
        "yellows_against": col("HY"),
        "reds_for": col("AR"),
        "reds_against": col("HR"),

        "odds_win": col("AvgA"),
        "odds_over2_5": col("Avg>2.5"),
        "odds_under2_5": col("Avg<2.5"),
        # handicap para a equipa visitante é o inverso
        "ah_line": -col("AHh"),
        "odds_ah": col("AvgAHA"),
    })

    tg = pd.concat([home, away], ignore_index=True)
    
    # --- Cantos (mercados estatísticos, sem odds) ---
    tg["corners_for"] = pd.to_numeric(tg["corners_for"], errors="coerce")
    tg["corners_against"] = pd.to_numeric(tg["corners_against"], errors="coerce")
    tg["corners_total"] = tg["corners_for"] + tg["corners_against"]
    
    # Totais do jogo (linhas comuns)
    tg["corners_over_8_5"] = tg["corners_total"] >= 9
    tg["corners_over_9_5"] = tg["corners_total"] >= 10
    tg["corners_over_10_5"] = tg["corners_total"] >= 11
    
    # Cantos da equipa (linhas comuns)
    tg["team_corners_over_4_5"] = tg["corners_for"] >= 5
    tg["team_corners_over_5_5"] = tg["corners_for"] >= 6
    
    # “Equipa ganha cantos” (útil para tendência)
    tg["team_wins_corners"] = tg["corners_for"] > tg["corners_against"]

    tg["goal_diff"] = tg["gf"] - tg["ga"]
    tg["over_1_5"] = tg["total_goals"] >= 2
    tg["over_3_5"] = tg["total_goals"] >= 4
    tg["team_win"] = tg["result"] == "W"
    tg["team_draw"] = tg["result"] == "D"
    tg["team_loss"] = tg["result"] == "L"
    tg["team_not_lose"] = tg["result"].isin(["W", "D"])

    # Eventos raros (para módulo de trading lay)
    tg = add_rare_event_columns(tg)

    return tg


def add_profit_columns(tg: pd.DataFrame) -> pd.DataFrame:
    tg = tg.copy()

    # 1X2 (vectorizado)
    tg["profit_team_win"] = np.where(tg["team_win"], tg["odds_win"] - 1.0, -1.0)
    tg.loc[tg["odds_win"].isna(), "profit_team_win"] = np.nan

    # Over/Under 2.5 (vectorizado)
    tg["profit_over2_5"] = np.where(tg["over_2_5"], tg["odds_over2_5"] - 1.0, -1.0)
    tg.loc[tg["odds_over2_5"].isna(), "profit_over2_5"] = np.nan

    tg["profit_under2_5"] = np.where(tg["under_2_5"], tg["odds_under2_5"] - 1.0, -1.0)
    tg.loc[tg["odds_under2_5"].isna(), "profit_under2_5"] = np.nan

    # Handicap Asiático (vectorizado, incluindo push/meias vitórias)
    eps = 1e-9
    gd = pd.to_numeric(tg["goal_diff"], errors="coerce")
    line = pd.to_numeric(tg["ah_line"], errors="coerce")
    odds = pd.to_numeric(tg["odds_ah"], errors="coerce")
    margin = gd + line

    profit = np.full(len(tg), np.nan, dtype="float64")
    valid = (~gd.isna()) & (~line.isna()) & (~odds.isna())

    m = margin.to_numpy(dtype="float64", copy=False)
    o = odds.to_numpy(dtype="float64", copy=False)

    v = valid.to_numpy(copy=False)

    win = v & (m >= 0.5)
    profit[win] = o[win] - 1.0

    push = v & (np.abs(m) < eps)
    profit[push] = 0.0

    loss = v & (m <= -0.5)
    profit[loss] = -1.0

    halfwin = v & (np.abs(m - 0.25) < eps)
    profit[halfwin] = (o[halfwin] - 1.0) / 2.0

    halfloss = v & (np.abs(m + 0.25) < eps)
    profit[halfloss] = -0.5

    tg["profit_ah"] = profit

    return tg


# -----------------------------
# Colunas de eventos raros (para trading lay)
# -----------------------------

def add_rare_event_columns(tg: pd.DataFrame) -> pd.DataFrame:
    """
    Adiciona colunas booleanas de eventos raros ao team-games.
    Usadas pelo módulo de trading lay para identificar cenários improváveis.

    Colunas adicionadas:
    - win_by_3plus      : equipa ganha por 3+ golos de diferença (goleada pró)
    - heavy_loss        : equipa perde por 2+ golos de diferença (goleada contra)
    - team_scores_3plus : equipa marca 3 ou mais golos
    - concedes_3plus    : equipa sofre 3 ou mais golos
    - win_nil           : equipa ganha a zero (CS + vitória)
    - lose_nil          : equipa perde a zero (adversário com CS + vitória)
    - draw_0_0          : jogo termina 0-0
    - over_3_5_goals    : mais de 3.5 golos no total (alias; já existe over_3_5 mas convém ter explícito)
    - team_win_away     : vitória fora de casa (útil para filtrar underdogs)
    - no_score          : equipa não marca (complemento de team_scored)
    - no_concede        : equipa não sofre (já é clean_sheet mas torna explícito)
    """
    tg = tg.copy()
    gf = pd.to_numeric(tg["gf"], errors="coerce")
    ga = pd.to_numeric(tg["ga"], errors="coerce")
    gd = gf - ga

    tg["win_by_3plus"]      = (gd >= 3).fillna(False)
    tg["heavy_loss"]        = (gd <= -2).fillna(False)
    tg["team_scores_3plus"] = (gf >= 3).fillna(False)
    tg["concedes_3plus"]    = (ga >= 3).fillna(False)
    tg["win_nil"]           = ((gd > 0) & (ga == 0)).fillna(False)
    tg["lose_nil"]          = ((gd < 0) & (gf == 0)).fillna(False)
    tg["draw_0_0"]          = ((gf == 0) & (ga == 0)).fillna(False)
    tg["over_3_5_goals"]    = ((gf + ga) >= 4).fillna(False)
    tg["team_win_away"]     = ((tg["result"] == "W") & (tg["venue"] == "A")).fillna(False)
    tg["no_score"]          = (~tg["team_scored"].fillna(False).astype(bool))
    tg["no_concede"]        = tg["clean_sheet"].fillna(False).astype(bool)

    return tg



# -----------------------------
# Trading Lay (módulo)
# -----------------------------
# Premissa: para fazer lay de um cenário, queres que ele raramente aconteça.
# Para cada equipa (Total/Casa/Fora) avaliamos cenários e ordenamos do mais improvável (melhor para lay)
# para o mais provável.

# 12 cenários lay (conforme especificação)
# nome -> (coluna_evento, descrição)
LAY_SCENARIOS: Dict[str, Tuple[str, str]] = {
    # Resultado
    "Lay Vitória":            ("team_win",           "Equipa vence o jogo"),
    "Lay Derrota":            ("team_loss",          "Equipa perde o jogo"),
    "Lay Empate":             ("team_draw",          "Jogo termina empatado"),

    # Golos (totais do jogo)
    "Lay Over 1.5":           ("over_1_5",           "Mais de 1.5 golos no jogo"),
    "Lay Over 2.5":           ("over_2_5",           "Mais de 2.5 golos no jogo"),
    "Lay Over 3.5":           ("over_3_5",           "Mais de 3.5 golos no jogo"),
    "Lay Under 2.5":          ("under_2_5",          "Menos de 2.5 golos no jogo"),

    # Outros
    "Lay BTTS":               ("btts",              "Ambas as equipas marcam"),
    "Lay Clean Sheet":        ("clean_sheet",       "Equipa não sofre golos (clean sheet)"),
    "Lay Equipa Marca":       ("team_scored",       "Equipa marca (>=1 golo)"),

    # Cantos (totais do jogo)
    "Lay Cantos Over 8.5":    ("corners_over_8_5",  "Total de cantos Over 8.5"),
    "Lay Cantos Over 10.5":   ("corners_over_10_5", "Total de cantos Over 10.5"),
}


def _scopes_to_do(lay_scope: str) -> List[str]:
    s = (lay_scope or "Todos").strip().lower()
    if s in ("todos", "all", ""):
        return ["Casa", "Fora", "Total"]
    if s in ("casa", "home", "h"):
        return ["Casa"]
    if s in ("fora", "away", "a"):
        return ["Fora"]
    if s in ("total", "t"):
        return ["Total"]
    raise ValueError(f"--lay-scope inválido: {lay_scope}")


def _scope_subset(tg: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope == "Casa":
        return tg[tg["venue"] == "H"]
    if scope == "Fora":
        return tg[tg["venue"] == "A"]
    return tg


def compute_lay_team_context(
    tg: pd.DataFrame,
    *,
    min_games: int = 8,
    wilson_z: float = 1.96,
    scopes: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Camadas 2 e 3 do módulo lay:
    - Raridade de placares/extremos:
        perder por 3+ (perde_3plus), ganhar por 3+ (ganha_3plus), 0-0 (zero_zero),
        jogos sem marcar (sem_marcar), perdeu sem marcar (perde_sem_marcar)
    - Volatilidade:
        std(diff golos), std(total golos), std(pontos), CV(golos marcados)

    Retorna DF por league+team+scope.
    """
    scopes = scopes or ["Casa", "Fora", "Total"]
    df = tg.copy()

    # Eventos extremos (do ponto de vista da equipa)
    gd = pd.to_numeric(df["goal_diff"], errors="coerce")
    df["lose_by_3plus"] = (gd <= -3)
    df["win_by_3plus"] = (gd >= 3)

    df["draw_0_0"] = (pd.to_numeric(df["gf"], errors="coerce") == 0) & (pd.to_numeric(df["ga"], errors="coerce") == 0)
    df["no_score"] = (~df["team_scored"].fillna(False).astype(bool))
    df["lose_nil"] = ((df["result"] == "L") & (pd.to_numeric(df["gf"], errors="coerce") == 0))

    has_league = "league" in df.columns
    out_rows: List[dict] = []

    def _rate(g: pd.DataFrame, col: str) -> Tuple[float, float, float, int]:
        x = pd.to_numeric(g[col], errors="coerce").dropna().astype(int)
        n = int(x.shape[0])
        if n <= 0:
            return (np.nan, np.nan, np.nan, 0)
        k = int(x.sum())
        hit = k / n
        lo, hi = wilson_interval(k, n, z=wilson_z)
        return (hit, lo, hi, n)

    for scope in scopes:
        sub = _scope_subset(df, scope)
        gb = (["team"] if not has_league else ["league", "team"])
        for keys, g in sub.groupby(gb, dropna=False):
            lg, team = (keys if has_league else ("ALL", keys))
            n_games = int(g.shape[0])
            if n_games < min_games:
                continue

            lose3, _, lose3_hi, _ = _rate(g, "lose_by_3plus")
            win3,  _, win3_hi,  _ = _rate(g, "win_by_3plus")
            z00,   _, z00_hi,   _ = _rate(g, "draw_0_0")
            nos,   _, nos_hi,   _ = _rate(g, "no_score")
            lnil,  _, lnil_hi,  _ = _rate(g, "lose_nil")

            # Volatilidade
            goal_diff_std = float(pd.to_numeric(g["goal_diff"], errors="coerce").std(ddof=0))
            total_goals_std = float(pd.to_numeric(g["total_goals"], errors="coerce").std(ddof=0))
            points_std = float(pd.to_numeric(g["points"], errors="coerce").std(ddof=0))
            gf_mean = float(pd.to_numeric(g["gf"], errors="coerce").mean())
            gf_std = float(pd.to_numeric(g["gf"], errors="coerce").std(ddof=0))
            cv_gf = safe_div(gf_std, gf_mean) if gf_mean and not pd.isna(gf_mean) else np.nan

            out_rows.append({
                "league": lg,
                "team": team,
                "scope": scope,
                "perde_3plus": lose3,
                "perde_3plus_hi": lose3_hi,
                "ganha_3plus": win3,
                "ganha_3plus_hi": win3_hi,
                "zero_zero": z00,
                "zero_zero_hi": z00_hi,
                "sem_marcar": nos,
                "sem_marcar_hi": nos_hi,
                "perde_sem_marcar": lnil,
                "perde_sem_marcar_hi": lnil_hi,
                "vol_std_diff_golos": goal_diff_std,
                "vol_std_total_golos": total_goals_std,
                "vol_std_pontos": points_std,
                "vol_cv_golos_marcados": cv_gf,
            })

    return pd.DataFrame(out_rows)


def build_lay_tables(
    tg: pd.DataFrame,
    *,
    min_games: int = 8,
    lay_threshold: float = 0.35,
    lay_scope: str = "Todos",
    lay_top: int = 5,
    wilson_z: float = 1.96,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Constrói:
    - lay_candidatos: todos os cenários (por equipa/scope), com hit_rate, IC Wilson, edge_vs_liga e lay_score
    - lay_top_por_equipa: top N por equipa/scope (resumo executivo), preferindo candidatos (flag_candidato=True)

    lay_score = (1 - hit_rate) × √n × (1 + confidence_weight)
    confidence_weight = max(0, (0.40 - wilson_hi) / 0.40)   (bónus se o IC superior < 40%)
    flag_candidato = (hit_rate <= lay_threshold) e (wilson_hi <= 0.40)
    """
    df = tg.copy()
    has_league = "league" in df.columns
    scopes = _scopes_to_do(lay_scope)

    # -----------------------------
    # Base da liga (para edge_vs_liga)
    # -----------------------------
    base_rates: Dict[Tuple[str, str, str], float] = {}  # (league, scope, scenario) -> mean

    for scope in scopes:
        sub = _scope_subset(df, scope)
        if has_league:
            gb = ["league"]
            for (lg,), g in sub.groupby(gb, dropna=False):
                for scen, (col, _) in LAY_SCENARIOS.items():
                    if col not in g.columns:
                        continue
                    x = pd.to_numeric(g[col], errors="coerce").dropna().astype(float)
                    if x.empty:
                        continue
                    base_rates[(str(lg), scope, scen)] = float(x.mean())
        else:
            for scen, (col, _) in LAY_SCENARIOS.items():
                if col not in sub.columns:
                    continue
                x = pd.to_numeric(sub[col], errors="coerce").dropna().astype(float)
                if x.empty:
                    continue
                base_rates[("ALL", scope, scen)] = float(x.mean())

    # -----------------------------
    # Cenários lay por equipa/scope
    # -----------------------------
    rows: List[dict] = []

    def _league_key(lg) -> str:
        return str(lg) if not pd.isna(lg) else "—"

    for scope in scopes:
        sub = _scope_subset(df, scope)

        gb = (["team"] if not has_league else ["league", "team"])
        for keys, g in sub.groupby(gb, dropna=False):
            lg, team = (keys if has_league else ("ALL", keys))
            lgk = _league_key(lg)

            for scen, (col, desc) in LAY_SCENARIOS.items():
                if col not in g.columns:
                    continue

                x = pd.to_numeric(g[col], errors="coerce").dropna().astype(int)
                n = int(x.shape[0])
                if n < min_games:
                    continue

                k = int(x.sum())
                hit = k / n
                lo, hi = wilson_interval(k, n, z=wilson_z)

                league_mean = base_rates.get((lgk if has_league else "ALL", scope, scen), np.nan)
                edge_vs_liga = (hit - league_mean) if not pd.isna(league_mean) else np.nan

                conf_w = 0.0
                if not pd.isna(hi):
                    conf_w = max(0.0, (0.40 - hi) / 0.40)
                    conf_w = min(1.0, conf_w)

                lay_score = (1.0 - hit) * math.sqrt(n) * (1.0 + conf_w)

                flag_candidato = bool((hit <= lay_threshold) and (not pd.isna(hi)) and (hi <= 0.40))

                rows.append({
                    "league": lgk if has_league else "ALL",
                    "team": str(team),
                    "scope": scope,
                    "cenario_lay": scen,
                    "descricao": desc,
                    "jogos": n,
                    "hit_rate": hit,
                    "wilson_lo": lo,
                    "wilson_hi": hi,
                    "edge_vs_liga": edge_vs_liga,
                    "confidence_weight": conf_w,
                    "lay_score": lay_score,
                    "flag_candidato": flag_candidato,
                })

    lay_df = pd.DataFrame(rows)
    if lay_df.empty:
        return lay_df, lay_df

    # juntar contexto (raridade + volatilidade)
    ctx = compute_lay_team_context(df, min_games=min_games, wilson_z=wilson_z, scopes=scopes)
    if not ctx.empty:
        lay_df = lay_df.merge(ctx, on=["league", "team", "scope"], how="left")

    lay_df = lay_df.sort_values(
        ["league", "scope", "lay_score", "hit_rate"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)

    # Top por equipa/scope (preferindo candidatos)
    top_parts = []
    for keys, g in lay_df.groupby(["league", "team", "scope"], dropna=False):
        g = g.sort_values(["flag_candidato", "lay_score"], ascending=[False, False])
        g_pref = g[g["flag_candidato"] == True].head(lay_top)
        if g_pref.empty:
            g_pref = g.head(lay_top)
        top_parts.append(g_pref)

    lay_top_df = pd.concat(top_parts, ignore_index=True) if top_parts else pd.DataFrame()
    lay_top_df = lay_top_df.sort_values(["league", "team", "scope", "lay_score"], ascending=[True, True, True, False]).reset_index(drop=True)

    return lay_df, lay_top_df


def render_lay_section_md(
    league: str,
    team: str,
    lay_df: Optional[pd.DataFrame],
    *,
    top_n: int = 5,
) -> str:
    """Gera a secção Trading Lay em Markdown para um clube."""
    if lay_df is None or lay_df.empty:
        return ""

    d = lay_df[(lay_df["league"] == league) & (lay_df["team"] == team)].copy()
    if d.empty:
        return ""

    lines: List[str] = []
    lines.append("## Trading Lay")
    lines.append("")
    lines.append("Cenários raros (bons candidatos a lay) — com IC de Wilson, edge vs liga e score composto.")
    lines.append("")

    for scope in ["Casa", "Fora", "Total"]:
        ds = d[d["scope"] == scope].copy()
        if ds.empty:
            continue

        ds = ds.sort_values(["flag_candidato", "lay_score"], ascending=[False, False]).head(top_n)

        t = ds[["cenario_lay", "jogos", "hit_rate", "wilson_hi", "edge_vs_liga", "lay_score", "flag_candidato"]].copy()
        t["hit_rate"] = t["hit_rate"].map(_pct)
        t["wilson_hi"] = t["wilson_hi"].map(_pct)
        t["edge_vs_liga"] = t["edge_vs_liga"].map(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f} pp")
        t["lay_score"] = t["lay_score"].map(_num)
        t["flag_candidato"] = t["flag_candidato"].map(lambda x: "✅" if bool(x) else "")

        lines.append(f"### {scope}")
        lines.append("")
        lines.append(t.to_markdown(index=False))
        lines.append("")

        # Contexto adicional (1 linha)
        extra_cols = [
            "perde_3plus", "ganha_3plus", "zero_zero", "sem_marcar", "perde_sem_marcar",
            "vol_std_diff_golos", "vol_std_total_golos", "vol_std_pontos", "vol_cv_golos_marcados",
        ]
        avail = [c for c in extra_cols if c in ds.columns]
        if avail:
            r = ds.iloc[0:1][avail].copy()
            for c in ["perde_3plus", "ganha_3plus", "zero_zero", "sem_marcar", "perde_sem_marcar"]:
                if c in r.columns:
                    r[c] = r[c].map(_pct)
            for c in ["vol_std_diff_golos", "vol_std_total_golos", "vol_std_pontos", "vol_cv_golos_marcados"]:
                if c in r.columns:
                    r[c] = r[c].map(_num)
            lines.append("**Raridade/volatilidade (contexto):**")
            lines.append("")
            lines.append(r.to_markdown(index=False))
            lines.append("")

    return "\n".join(lines)


# -----------------------------
# Métricas por equipa
# -----------------------------

def team_summary(tg: pd.DataFrame) -> pd.DataFrame:
    """Resumo por liga + equipa, com separação Casa/Fora/Total.

    Acrescenta índices derivados:
    - conversion_rate: gf / shots_for
    - sot_pct: sot_for / shots_for
    - xg_impl: sot_for * 0.33 (heurística simples)
    - xg_overperf: gf - xg_impl (positivo = acima do "esperado" pelo SOT)
    - defensive_solidity: ga / shots_against
    """
    def summarise(df: pd.DataFrame, scope: str) -> pd.DataFrame:
        group_cols = ["league", "team"] if "league" in df.columns else ["team"]

        out = (
            df.groupby(group_cols, dropna=True)
            .agg(
                jogos=("match_id", "count"),
                ppg=("points", "mean"),
                **{
                    "vit%": ("team_win", "mean"),
                    "emp%": ("team_draw", "mean"),
                    "der%": ("team_loss", "mean"),
                    "golos_marcados": ("gf", "mean"),
                    "golos_sofridos": ("ga", "mean"),
                    "diff_golos": ("goal_diff", "mean"),
                    "marca%": ("team_scored", "mean"),
                    "CS%": ("clean_sheet", "mean"),
                    "BTTS%": ("btts", "mean"),
                    "O2.5%": ("over_2_5", "mean"),
                    "U2.5%": ("under_2_5", "mean"),
                    "remates": ("shots_for", "mean"),
                    "remates_sofridos": ("shots_against", "mean"),
                    "SOT": ("sot_for", "mean"),
                    "SOT_sofridos": ("sot_against", "mean"),
                    "cantos": ("corners_for", "mean"),
                    "cantos_sofridos": ("corners_against", "mean"),
                    "amarelos": ("yellows_for", "mean"),
                    "amarelos_sofridos": ("yellows_against", "mean"),

                    # somas para rácios mais robustos
                    "gf_sum": ("gf", "sum"),
                    "ga_sum": ("ga", "sum"),
                    "shots_sum": ("shots_for", "sum"),
                    "shots_against_sum": ("shots_against", "sum"),
                    "sot_sum": ("sot_for", "sum"),
                },
            )
            .reset_index()
        )

        # índices derivados (com base em somas)
        out["conversion_rate"] = out.apply(lambda r: safe_div(r["gf_sum"], r["shots_sum"]), axis=1)
        out["sot_pct"] = out.apply(lambda r: safe_div(r["sot_sum"], r["shots_sum"]), axis=1)
        out["xg_impl"] = out["sot_sum"] * 0.33 / out["jogos"].replace(0, np.nan)  # por jogo
        out["xg_overperf"] = out["golos_marcados"] - out["xg_impl"]
        out["defensive_solidity"] = out.apply(lambda r: safe_div(r["ga_sum"], r["shots_against_sum"]), axis=1)

        # limpeza das colunas auxiliares de somas (mantém, mas no fim pode ocultar nos relatórios)
        out["scope"] = scope
        return out

    overall = summarise(tg, "Total")
    home = summarise(tg[tg["venue"] == "H"], "Casa")
    away = summarise(tg[tg["venue"] == "A"], "Fora")

    out = pd.concat([overall, home, away], ignore_index=True)

    out["scope_ord"] = out["scope"].map({"Total": 0, "Casa": 1, "Fora": 2}).fillna(9)
    sort_cols = ["scope_ord", "ppg"]
    if "league" in out.columns:
        sort_cols = ["league"] + sort_cols
    out = out.sort_values(sort_cols, ascending=[True] * (len(sort_cols)-1) + [False]).drop(columns=["scope_ord"])

    return out


    overall = summarise(tg, "Total")
    home = summarise(tg[tg["venue"] == "H"], "Casa")
    away = summarise(tg[tg["venue"] == "A"], "Fora")

    out = pd.concat([overall, home, away], ignore_index=True)

    # Ordenação
    out["scope_ord"] = out["scope"].map({"Total": 0, "Casa": 1, "Fora": 2}).fillna(9)
    sort_cols = ["scope_ord", "ppg"]
    if "league" in out.columns:
        sort_cols = ["league"] + sort_cols
    out = out.sort_values(sort_cols, ascending=[True] * (len(sort_cols)-1) + [False]).drop(columns=["scope_ord"])

    return out


# -----------------------------
# Mercados (taxa de acerto + ROI quando possível)
# -----------------------------

# -----------------------------
# Mercados (taxa de acerto + ROI quando possível + value estimado)
# -----------------------------

# Estrutura: nome -> (coluna_evento_booleano, coluna_profit, coluna_odds_media)
MARKETS: Dict[str, Tuple[Optional[str], Optional[str], Optional[str]]] = {
    # nome: (coluna_booleano, coluna_profit, coluna_odds)
    "Vitória (1X2)": ("team_win", "profit_team_win", "odds_win"),
    "Over 2.5 golos": ("over_2_5", "profit_over2_5", "odds_over2_5"),
    "Under 2.5 golos": ("under_2_5", "profit_under2_5", "odds_under2_5"),

    # AH: o evento depende da linha; aqui usamos apenas ROI e odds médias (quando existirem)
    "Handicap Asiático (AH)": (None, "profit_ah", "odds_ah"),

    # Mercados estatísticos sem odds (no CSV típico)
    "Casa marca (>=1)": ("team_scored", None, None),
    "Clean sheet": ("clean_sheet", None, None),
    "Ambas marcam (BTTS)": ("btts", None, None),
    "Over 1.5 golos": ("over_1_5", None, None),
    "Over 3.5 golos": ("over_3_5", None, None),
    "Cantos total Over 8.5": ("corners_over_8_5", None, None),
    "Cantos total Over 9.5": ("corners_over_9_5", None, None),
    "Cantos total Over 10.5": ("corners_over_10_5", None, None),
    "Cantos equipa Over 4.5": ("team_corners_over_4_5", None, None),
    "Cantos equipa Over 5.5": ("team_corners_over_5_5", None, None),
    "Equipa ganha cantos": ("team_wins_corners", None, None),
}


def build_market_table(
    tg: pd.DataFrame,
    min_games: int = 8,
    exclude_team_from_league_avg: bool = False,
    *,
    form_window: int = 5,
    trend_threshold: float = 0.15,
    wilson_z: float = 1.96,
    extra_group_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Tabela de mercados por equipa.

    Inclui:
    - hit_rate (quando aplicável)
    - edge_vs_liga (vs média da mesma liga)
    - ROI (quando existem odds)
    - odds_avg + prob_implícita + value_estimado (quando existe odds e hit_rate)
    - std (binomial) + IC de Wilson para hit_rate
    - forma_recente_N + alerta_tendencia_inversa (quando aplicável)

    extra_group_cols permite segmentações (ex.: por season/phase).
    """
    has_league = "league" in tg.columns
    rows: List[dict] = []

    extra_group_cols = extra_group_cols or []

    def scope_name(v: str) -> str:
        return {"H": "Casa", "A": "Fora"}.get(v, v)

    # -----------------------------
    # Bases da liga (para edge)
    # -----------------------------
    league_base_mean: Dict[Tuple, Dict[str, float]] = {}
    league_base_sumcnt: Dict[Tuple, Dict[str, Tuple[float, int]]] = {}
    team_sumcnt: Dict[Tuple, Dict[str, Tuple[float, int]]] = {}

    def _sum_cnt(s: pd.Series) -> Tuple[float, int]:
        x = pd.to_numeric(s, errors="coerce").dropna()
        return float(x.sum()), int(x.shape[0])

    # group key para bases de liga inclui extra (ex.: season/phase)
    league_key_cols = (["league"] if has_league else ["_league_dummy"]) + extra_group_cols
    df_base = tg.copy()
    if not has_league:
        df_base["_league_dummy"] = "ALL"

    for lkeys, gl in df_base.groupby(league_key_cols, dropna=False):
        league_base_mean[lkeys] = {}
        league_base_sumcnt[lkeys] = {}
        for mname, (out_col, _, _) in MARKETS.items():
            if out_col is not None and out_col in gl.columns:
                sm, ct = _sum_cnt(gl[out_col])
                league_base_sumcnt[lkeys][mname] = (sm, ct)
                league_base_mean[lkeys][mname] = (sm / ct) if ct > 0 else np.nan

    if exclude_team_from_league_avg:
        gb_team = (["team"] if not has_league else ["league", "team"]) + extra_group_cols
        for keys, g in tg.groupby(gb_team, dropna=False):
            # keys: (league?, team, extra...)
            if has_league:
                lg = keys[0]
                team = keys[1]
                extra_vals = keys[2:]
            else:
                lg = "ALL"
                team = keys[0]
                extra_vals = keys[1:]
            tkey = (lg, team, *extra_vals)

            team_sumcnt[tkey] = {}
            for mname, (out_col, _, _) in MARKETS.items():
                if out_col is not None and out_col in g.columns:
                    team_sumcnt[tkey][mname] = _sum_cnt(g[out_col])

    def _league_base(lg: str, team: str, extra_vals: Tuple, mname: str) -> float:
        lkey = (lg, *extra_vals)
        base = league_base_mean.get(lkey, {}).get(mname, np.nan)
        if not exclude_team_from_league_avg:
            return base

        tot_sum, tot_cnt = league_base_sumcnt.get(lkey, {}).get(mname, (np.nan, 0))
        tkey = (lg, team, *extra_vals)
        team_sum, team_cnt = team_sumcnt.get(tkey, {}).get(mname, (0.0, 0))

        denom = tot_cnt - team_cnt
        if denom < max(10, min_games):
            return base
        return (tot_sum - team_sum) / denom

    # -----------------------------
    # Cálculo por grupo
    # -----------------------------
    def _compute_market_rows(g: pd.DataFrame, lg: str, team: str, scope: str, n: int, extra_vals: Tuple) -> List[dict]:
        out_rows: List[dict] = []
        g_sorted = g.sort_values(["date", "match_id"], kind="mergesort")

        for mname, (out_col, prof_col, odds_col) in MARKETS.items():
            # hit rate + IC/volatilidade
            if out_col and out_col in g_sorted.columns:
                x = pd.to_numeric(g_sorted[out_col], errors="coerce").dropna()
                ct = int(x.shape[0])
                k = float(x.sum())
                hit = (k / ct) if ct > 0 else np.nan
                std = math.sqrt(hit * (1 - hit)) if ct > 0 and not pd.isna(hit) else np.nan
                w_lo, w_hi = wilson_interval(k, ct, z=wilson_z)
                recent = float(x.tail(form_window).mean()) if ct > 0 else np.nan
                alerta = bool((not pd.isna(recent)) and (not pd.isna(hit)) and ((hit - recent) >= trend_threshold))
            else:
                ct = 0
                k = np.nan
                hit = np.nan
                std = np.nan
                w_lo, w_hi = (np.nan, np.nan)
                recent = np.nan
                alerta = False

            base = _league_base(lg, team, extra_vals, mname) if out_col else np.nan
            edge = (hit - base) if out_col else np.nan

            # ROI
            roi = float(pd.to_numeric(g_sorted[prof_col], errors="coerce").mean()) if prof_col else np.nan

            # odds + value
            if odds_col and odds_col in g_sorted.columns:
                odds_avg = float(pd.to_numeric(g_sorted[odds_col], errors="coerce").mean())
            else:
                odds_avg = np.nan

            prob_impl = safe_div(1.0, odds_avg) if not pd.isna(odds_avg) else np.nan
            value_est = (safe_div(hit, prob_impl) - 1.0) if (not pd.isna(hit) and not pd.isna(prob_impl) and prob_impl > 0) else np.nan

            row = {
                "league": lg,
                "team": team,
                "scope": scope,
                "market": mname,
                "jogos": n,
                "n_eventos": ct if out_col else np.nan,  # n usado no cálculo do hit (pode diferir se houver NaN)
                "hit_rate": hit,
                "hit_std": std,
                "wilson_lo": w_lo,
                "wilson_hi": w_hi,
                "edge_vs_liga": edge,
                "roi_unid_por_aposta": roi,
                "odds_avg": odds_avg,
                "prob_impl": prob_impl,
                "value_estimado": value_est,
                f"form_recent_{form_window}": recent,
                "alerta_tendencia_inversa": alerta,
            }

            # adicionar colunas de segmentação
            for col, val in zip(extra_group_cols, extra_vals):
                row[col] = val

            out_rows.append(row)

        return out_rows

    # Casa/Fora
    gb_cols = (["team", "venue"] if not has_league else ["league", "team", "venue"]) + extra_group_cols
    for keys, g in tg.groupby(gb_cols, dropna=False):
        if has_league:
            lg, team, venue = keys[:3]
            extra_vals = tuple(keys[3:])
        else:
            team, venue = keys[:2]
            lg = "ALL"
            extra_vals = tuple(keys[2:])

        n = len(g)
        if n < min_games:
            continue
        rows.extend(_compute_market_rows(g, lg, team, scope_name(venue), n, extra_vals))

    # Total
    gb_cols = (["team"] if not has_league else ["league", "team"]) + extra_group_cols
    for keys, g in tg.groupby(gb_cols, dropna=False):
        if has_league:
            lg, team = keys[:2]
            extra_vals = tuple(keys[2:])
        else:
            team = keys[0]
            lg = "ALL"
            extra_vals = tuple(keys[1:])

        n = len(g)
        if n < min_games:
            continue
        rows.extend(_compute_market_rows(g, lg, team, "Total", n, extra_vals))

    return pd.DataFrame(rows)



# -----------------------------
# Série temporal (rolling)
# -----------------------------

def team_timeseries(tg: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    out = []
    sort_cols = ["date", "match_id"]
    tg = tg.sort_values(sort_cols)

    gb_cols = ["team"]
    if "league" in tg.columns:
        gb_cols = ["league", "team"]

    for keys, g in tg.groupby(gb_cols):
        if "league" in tg.columns:
            lg, team = keys
        else:
            lg, team = "ALL", keys

        g = g.sort_values(sort_cols).copy()
        g["jogo_n"] = range(1, len(g) + 1)

        for col in ["points", "gf", "ga", "goal_diff", "over_2_5", "under_2_5", "btts", "team_scored", "clean_sheet"]:
            g[f"roll{window}_{col}"] = pd.to_numeric(g[col], errors="coerce").rolling(window, min_periods=1).mean()

        keep = ["league", "team", "date", "venue", "opponent", "gf", "ga", "result", "points", "jogo_n"] + [c for c in g.columns if c.startswith(f"roll{window}_")]
        out.append(g[keep])

    return pd.concat(out, ignore_index=True)


# -----------------------------
# Head-to-head (H2H)
# -----------------------------

def head_to_head(
    tg: pd.DataFrame,
    team_a: str,
    team_b: str,
    *,
    league: Optional[str] = None,
    last_n: int = 5,
    min_games: int = 3,
) -> pd.DataFrame:
    """Análise de confrontos directos entre duas equipas.

    Retorna um DataFrame com duas linhas:
    - "Histórico" (todos os jogos encontrados)
    - f"Últimos {last_n}" (tendência recente)

    Métricas:
    - jogos, vit/emp/der para a Team A
    - golos médios marcados/sofridos por Team A
    - BTTS%, Over/Under 2.5%
    - quem costuma marcar: marca% Team A / marca% Team B
    """
    df = tg.copy()

    if league is not None:
        df = df[df["league"] == league].copy()

    mask = (
        ((df["team"] == team_a) & (df["opponent"] == team_b)) |
        ((df["team"] == team_b) & (df["opponent"] == team_a))
    )
    h = df[mask].copy()
    if h.empty:
        return pd.DataFrame()

    # Garantir ordem temporal por jogo (cada jogo aparece 2x no tg; deduplicar por match_id)
    games = (
        h.sort_values(["date", "match_id"], kind="mergesort")
         .drop_duplicates(subset=["match_id"])
         .copy()
    )

    def _row(gm: pd.DataFrame, label: str) -> dict:
        # reconstruir stats do ponto de vista do Team A
        a = tg[(tg["match_id"].isin(gm["match_id"])) & (tg["team"] == team_a) & (tg["opponent"] == team_b)].copy()
        b = tg[(tg["match_id"].isin(gm["match_id"])) & (tg["team"] == team_b) & (tg["opponent"] == team_a)].copy()

        n = int(gm.shape[0])
        if n < min_games:
            return {"amostra": label, "jogos": n}

        # resultados do Team A
        vit = float((a["result"] == "W").mean()) if not a.empty else np.nan
        emp = float((a["result"] == "D").mean()) if not a.empty else np.nan
        der = float((a["result"] == "L").mean()) if not a.empty else np.nan

        out = {
            "amostra": label,
            "jogos": n,
            "TeamA_vit%": vit,
            "TeamA_emp%": emp,
            "TeamA_der%": der,
            "TeamA_gf": float(pd.to_numeric(a["gf"], errors="coerce").mean()) if not a.empty else np.nan,
            "TeamA_ga": float(pd.to_numeric(a["ga"], errors="coerce").mean()) if not a.empty else np.nan,
            "BTTS%": float(pd.to_numeric(a["btts"], errors="coerce").mean()) if not a.empty else np.nan,
            "O2.5%": float(pd.to_numeric(a["over_2_5"], errors="coerce").mean()) if not a.empty else np.nan,
            "U2.5%": float(pd.to_numeric(a["under_2_5"], errors="coerce").mean()) if not a.empty else np.nan,
            "TeamA_marca%": float(pd.to_numeric(a["team_scored"], errors="coerce").mean()) if not a.empty else np.nan,
            "TeamB_marca%": float(pd.to_numeric(b["team_scored"], errors="coerce").mean()) if not b.empty else np.nan,
        }
        return out

    all_row = _row(games, "Histórico")
    last_row = _row(games.tail(last_n), f"Últimos {min(last_n, games.shape[0])}")

    return pd.DataFrame([all_row, last_row])

# -----------------------------
# Relatórios por equipa (Markdown)
# -----------------------------

def pick_best_markets(market_table: pd.DataFrame, league: str, team: str, scope: str, top_n: int = 3):
    d = market_table[(market_table["league"] == league) & (market_table["team"] == team) & (market_table["scope"] == scope)].copy()

    # Consistência: edge ponderado por amostra (cresce ~sqrt(n))
    e = d.dropna(subset=["edge_vs_liga"]).copy()
    e["score_edge"] = e["edge_vs_liga"] * np.sqrt(e["jogos"])
    top_edge = e.sort_values("score_edge", ascending=False).head(top_n)

    # ROI (quando existe)
    r = d.dropna(subset=["roi_unid_por_aposta"]).copy()
    top_roi = r.sort_values("roi_unid_por_aposta", ascending=False).head(top_n)

    # Value estimado (quando existe)
    v = d.dropna(subset=["value_estimado"]).copy()
    top_value = v.sort_values("value_estimado", ascending=False).head(top_n)

    return top_edge, top_roi, top_value



def render_team_report(league: str, team: str, summary_df: pd.DataFrame, market_table: pd.DataFrame, lay_df: Optional[pd.DataFrame] = None, lay_top_n: int = 5) -> str:
    lines: List[str] = []
    lines.append(f"# {team} ({league})")
    lines.append("")
    lines.append("## Resumo (Total / Casa / Fora)")
    lines.append("")
    s = summary_df[(summary_df["league"] == league) & (summary_df["team"] == team)].copy()
    s = s.sort_values("scope", key=lambda c: c.map({"Total": 0, "Casa": 1, "Fora": 2}).fillna(9))

    cols_main = [
        "scope", "jogos", "ppg", "vit%", "emp%", "der%",
        "golos_marcados", "golos_sofridos", "diff_golos",
        "marca%", "CS%", "BTTS%", "O2.5%", "U2.5%",
    ]
    s2 = s[cols_main].copy()

    s2["ppg"] = s2["ppg"].map(_num)
    for c in ["vit%", "emp%", "der%", "marca%", "CS%", "BTTS%", "O2.5%", "U2.5%"]:
        s2[c] = s2[c].map(_pct)
    for c in ["golos_marcados", "golos_sofridos", "diff_golos"]:
        s2[c] = s2[c].map(_num)

    lines.append(s2.to_markdown(index=False))
    lines.append("")

    # índices derivados (por jogo onde faz sentido)
    lines.append("## Índices derivados (qualidade / eficácia)")
    lines.append("")
    cols_q = ["scope", "conversion_rate", "sot_pct", "xg_impl", "xg_overperf", "defensive_solidity"]
    q = s[cols_q].copy()
    q["conversion_rate"] = q["conversion_rate"].map(_num)
    q["sot_pct"] = q["sot_pct"].map(_num)
    q["xg_impl"] = q["xg_impl"].map(_num)
    q["xg_overperf"] = q["xg_overperf"].map(_num)
    q["defensive_solidity"] = q["defensive_solidity"].map(_num)
    lines.append(q.to_markdown(index=False))
    lines.append("")

    recent_col = next((c for c in market_table.columns if c.startswith("form_recent_")), None)

    for scope in ["Casa", "Fora", "Total"]:
        lines.append(f"## Melhores mercados ({scope})")
        lines.append("")
        top_edge, top_roi, top_value = pick_best_markets(market_table, league, team, scope, top_n=4)

        if not top_edge.empty:
            cols = ["market", "jogos", "hit_rate", "wilson_lo", "wilson_hi", "edge_vs_liga"]
            if recent_col is not None and recent_col in top_edge.columns:
                cols.append(recent_col)
            cols.append("alerta_tendencia_inversa")
            t = top_edge[cols].copy()
            t["hit_rate"] = t["hit_rate"].map(_pct)
            t["wilson_lo"] = t["wilson_lo"].map(_pct)
            t["wilson_hi"] = t["wilson_hi"].map(_pct)
            t["edge_vs_liga"] = t["edge_vs_liga"].map(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f} pp")
            if recent_col is not None and recent_col in t.columns:
                t[recent_col] = t[recent_col].map(_pct)
            t["alerta_tendencia_inversa"] = t["alerta_tendencia_inversa"].map(lambda x: "⚠️" if bool(x) else "")
            lines.append("**Mais acima da média da liga (edge) — com IC e forma recente:**")
            lines.append("")
            lines.append(t.to_markdown(index=False))
            lines.append("")
        else:
            lines.append("Sem mercados com edge suficiente (amostra pequena ou colunas em falta).")
            lines.append("")

        if not top_value.empty:
            t = top_value[["market", "jogos", "hit_rate", "odds_avg", "prob_impl", "value_estimado"]].copy()
            t["hit_rate"] = t["hit_rate"].map(_pct)
            t["odds_avg"] = t["odds_avg"].map(_num)
            t["prob_impl"] = t["prob_impl"].map(_pct)
            t["value_estimado"] = t["value_estimado"].map(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f}%")
            lines.append("**Maior value estimado (hit rate vs prob. implícita das odds):**")
            lines.append("")
            lines.append(t.to_markdown(index=False))
            lines.append("")
        else:
            lines.append("Sem value estimado (odds em falta) ou sem hit_rate para o mercado.")
            lines.append("")

        if not top_roi.empty:
            t = top_roi[["market", "jogos", "roi_unid_por_aposta"]].copy()
            t["roi_unid_por_aposta"] = t["roi_unid_por_aposta"].map(_roi)
            lines.append("**Melhor ROI histórico (quando há odds):**")
            lines.append("")
            lines.append(t.to_markdown(index=False))
            lines.append("")
        else:
            lines.append("Sem ROI disponível (odds em falta) ou amostra pequena.")
            lines.append("")

    
    # Trading Lay (opcional)
    lay_section = render_lay_section_md(league, team, lay_df, top_n=lay_top_n)
    if lay_section:
        lines.append(lay_section)
    return "\n".join(lines)



# -----------------------------
# Excel
# -----------------------------

LEAGUE_NAMES = {
    "E0": "Premier League (Inglaterra)",
    "E1": "Championship (Inglaterra)",
    "F1": "Ligue 1 (França)",
    "I1": "Serie A (Itália)",
    "P1": "Liga Portugal",
}


def to_excel(out_path: Path, resumo: pd.DataFrame, mercados: pd.DataFrame, series: pd.DataFrame, mercados_fase: Optional[pd.DataFrame] = None, lay_candidatos: Optional[pd.DataFrame] = None, lay_top: Optional[pd.DataFrame] = None):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ligas = (
        resumo[["league"]]
        .drop_duplicates()
        .assign(nome=lambda d: d["league"].map(LEAGUE_NAMES).fillna("—"))
        .merge(
            series.groupby("league", as_index=False).agg(jogos_registos=("team", "count")),
            on="league",
            how="left",
        )
        .sort_values("league")
    )

    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        ligas.to_excel(xw, sheet_name="Ligas", index=False)
        resumo.to_excel(xw, sheet_name="Resumo", index=False)
        mercados.to_excel(xw, sheet_name="Mercados", index=False)
        if mercados_fase is not None and not mercados_fase.empty:
            mercados_fase.to_excel(xw, sheet_name="Mercados_Fases", index=False)
        if lay_candidatos is not None and not lay_candidatos.empty:
            lay_candidatos.to_excel(xw, sheet_name="Lay_Candidatos", index=False)
            # compatibilidade (dashboard antigo): mantém também o nome anterior
            lay_candidatos.to_excel(xw, sheet_name="TradingScenarios", index=False)
        if lay_top is not None and not lay_top.empty:
            lay_top.to_excel(xw, sheet_name="Lay_Top", index=False)
        series.to_excel(xw, sheet_name="SerieTemporal", index=False)



# -----------------------------
# Main
# -----------------------------

def main():
    ap = argparse.ArgumentParser(description="Analisar equipas e mercados a partir de CSVs (football-data).")
    ap.add_argument("--csv", type=str, default="", help="Caminho para um CSV específico (ex.: E0.csv). Se vazio, lê todos os CSVs da pasta (--csv-dir).")
    ap.add_argument("--csv-dir", type=str, default="", help="Pasta para ler todos os CSVs. Por omissão: a pasta onde está este script.")
    ap.add_argument("--pattern", type=str, default="*.csv", help="Padrão (glob) para escolher CSVs quando usa --csv-dir (ex.: 'E*.csv').")
    ap.add_argument("--outdir", type=str, default="output", help="Pasta de saída")
    ap.add_argument("--rolling", type=int, default=5, help="Janela para médias móveis (série temporal)")
    ap.add_argument("--form-window", type=int, default=5, help="N jogos recentes para forma_recente_N (mercados)")
    ap.add_argument("--trend-threshold", type=float, default=0.15, help="Diferença mínima (hit-histórico - forma_recente) para alerta_tendencia_inversa (ex.: 0.15 = 15pp)")
    ap.add_argument("--wilson-z", type=float, default=1.96, help="Z do IC de Wilson (1.96 ~ 95%)")
    ap.add_argument("--season-split", type=str, default="none", choices=["none", "halves", "thirds"], help="Segmentar por fase da época (none/halves/thirds)")
    ap.add_argument("--h2h", type=str, default="", help="Gerar relatório H2H (formato: 'Equipa A|Equipa B'). Não altera os outputs gerais.")
    ap.add_argument("--h2h-league", type=str, default="", help="Filtrar liga para o H2H (ex.: E0). Vazio = todas.")
    ap.add_argument("--min-games", type=int, default=8, help="Mínimo de jogos para incluir nos rankings")
    ap.add_argument("--leagues", type=str, default="", help="Filtrar ligas (Div) separadas por vírgulas, ex.: 'E0,I1'. Vazio = todas.")
    ap.add_argument("--split-by-league", action="store_true", help="Forçar geração de subpastas por liga (além do output combinado).")
    ap.add_argument("--edge-exclude-team", action="store_true", help="Calcular edge_vs_liga excluindo os jogos da própria equipa (leave-one-team-out), quando há amostra suficiente.")

    ap.add_argument("--lay", "--trading", dest="lay", action="store_true",
                    help="Activar o módulo Trading Lay (cenários improváveis, IC de Wilson, edge vs liga e lay_score).")
    ap.add_argument("--lay-threshold", "--trading-max-hit", dest="lay_threshold", type=float, default=0.35,
                    help="Threshold de hit_rate para marcar flag_candidato (ex.: 0.25 = muito agressivo).")
    ap.add_argument("--lay-scope", type=str, default="Todos", choices=["Todos", "Casa", "Fora", "Total"],
                    help="Contexto para o módulo lay (Todos/Casa/Fora/Total).")
    ap.add_argument("--lay-top", type=int, default=5,
                    help="Top N cenários por equipa (no ficheiro lay_top_por_equipa.csv e sheet Lay_Top).")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Fonte de dados:
    # - Se --csv for dado: lê um ficheiro
    # - Caso contrário: lê todos os CSVs da pasta (--csv-dir) ou, por omissão, a pasta onde está este script
    if args.csv.strip():
        csv_path = Path(args.csv)
        matches = read_matches(csv_path, default_league=infer_league_from_filename(csv_path), add_source=True)
        sources = [csv_path.name]
    else:
        base_dir = Path(args.csv_dir).resolve() if args.csv_dir.strip() else Path(__file__).resolve().parent
        matches = read_matches_from_dir(base_dir, pattern=args.pattern)
        sources = sorted(matches["source_file"].dropna().unique().tolist())

    if sources:
        log.info("Fontes CSV lidas (%s): %s%s", len(sources), ", ".join(sources[:12]), " ..." if len(sources) > 12 else "")

    # filtro de ligas
    if args.leagues.strip():
        keep = {x.strip() for x in args.leagues.split(",") if x.strip()}
        matches = matches[matches["league"].isin(keep)].copy()

    matches = add_season_phase(matches, split=args.season_split)

    tg = build_team_games(matches)
    tg = add_profit_columns(tg)

    resumo = team_summary(tg)
    mercados = build_market_table(
        tg,
        min_games=args.min_games,
        exclude_team_from_league_avg=args.edge_exclude_team,
        form_window=args.form_window,
        trend_threshold=args.trend_threshold,
        wilson_z=args.wilson_z,
    )
    
    mercados_fase = None
    if args.season_split != "none" and ("season" in tg.columns):
        mercados_fase = build_market_table(
            tg.dropna(subset=["season"]).copy(),
            min_games=args.min_games,
            exclude_team_from_league_avg=args.edge_exclude_team,
            form_window=args.form_window,
            trend_threshold=args.trend_threshold,
            wilson_z=args.wilson_z,
            extra_group_cols=["season", "phase"],
        )

    series = team_timeseries(tg, window=args.rolling)

    
    # Trading Lay (opcional)
    lay_candidatos = None
    lay_top_df = None
    if getattr(args, "lay", False):
        log.info("A calcular Trading Lay (cenários para lay)...")
        lay_candidatos, lay_top_df = build_lay_tables(
            tg,
            min_games=args.min_games,
            lay_threshold=args.lay_threshold,
            lay_scope=args.lay_scope,
            lay_top=args.lay_top,
            wilson_z=args.wilson_z,
        )

        if lay_candidatos is not None and not lay_candidatos.empty:
            lay_candidatos.to_csv(outdir / "lay_candidatos.csv", index=False)
            log.info("lay_candidatos.csv gerado (%d linhas).", len(lay_candidatos))
        else:
            log.warning("Nenhum cenário lay gerado (dados insuficientes ou colunas em falta).")

        if lay_top_df is not None and not lay_top_df.empty:
            lay_top_df.to_csv(outdir / "lay_top_por_equipa.csv", index=False)
            log.info("lay_top_por_equipa.csv gerado (%d linhas).", len(lay_top_df))


# Guardar CSVs (combinado)
    resumo.to_csv(outdir / "resumo_equipas.csv", index=False)
    mercados.to_csv(outdir / "mercados_equipas.csv", index=False)
    if mercados_fase is not None and not mercados_fase.empty:
        mercados_fase.to_csv(outdir / "mercados_equipas_fases.csv", index=False)
    series.to_csv(outdir / "serie_temporal_equipas.csv", index=False)

    # Excel combinado
    to_excel(outdir / "relatorio_equipas.xlsx", resumo, mercados, series, mercados_fase, lay_candidatos, lay_top_df)

    # Relatórios por equipa (combinado, por liga)
    reports_dir = outdir / "relatorios_equipas"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for (lg, team) in sorted(tg[["league", "team"]].dropna().drop_duplicates().itertuples(index=False, name=None)):
        md = render_team_report(lg, team, resumo, mercados, lay_candidatos if getattr(args, "lay", False) else None, lay_top_n=getattr(args, "lay_top", 5))
        safe = f"{lg}__{team}".replace("/", "_")
        (reports_dir / f"{safe}.md").write_text(md, encoding="utf-8")

    # Subpastas por liga (se houver várias ligas)
    leagues_found = sorted(tg["league"].dropna().unique().tolist())
    if args.split_by_league or len(leagues_found) > 1:
        for lg in leagues_found:
            sub = outdir / lg
            sub.mkdir(parents=True, exist_ok=True)

            # Reutiliza DataFrames já calculados (evita recomputações por liga)
            resumo_l = resumo[resumo["league"] == lg].copy()
            mercados_l = mercados[mercados["league"] == lg].copy()
            series_l = series[series["league"] == lg].copy()

            resumo_l.to_csv(sub / "resumo_equipas.csv", index=False)
            mercados_l.to_csv(sub / "mercados_equipas.csv", index=False)
            series_l.to_csv(sub / "serie_temporal_equipas.csv", index=False)
            mercados_fase_l = None
            if mercados_fase is not None and not mercados_fase.empty:
                mercados_fase_l = mercados_fase[mercados_fase["league"] == lg].copy()
            lay_candidatos_l = lay_candidatos[lay_candidatos["league"] == lg].copy() if lay_candidatos is not None and not lay_candidatos.empty else None
            lay_top_l = lay_top_df[lay_top_df["league"] == lg].copy() if lay_top_df is not None and not lay_top_df.empty else None
            to_excel(sub / "relatorio_equipas.xlsx", resumo_l, mercados_l, series_l, mercados_fase_l, lay_candidatos_l, lay_top_l)

            rep_l = sub / "relatorios_equipas"
            rep_l.mkdir(parents=True, exist_ok=True)
            teams_l = sorted(tg[tg["league"] == lg]["team"].dropna().unique())
            for team in teams_l:
                md = render_team_report(lg, team, resumo_l, mercados_l, lay_candidatos_l if (getattr(args, "lay", False) and lay_candidatos_l is not None) else None, lay_top_n=getattr(args, "lay_top", 5))
                safe = f"{team}".replace("/", "_")
                (rep_l / f"{safe}.md").write_text(md, encoding="utf-8")

    
    # Relatório H2H (opcional)
    if args.h2h.strip():
        if "|" in args.h2h:
            team_a, team_b = [x.strip() for x in args.h2h.split("|", 1)]
            lg_h2h = args.h2h_league.strip() or None
            h2h_df = head_to_head(tg, team_a, team_b, league=lg_h2h, last_n=args.form_window, min_games=max(3, args.min_games//2))
            if h2h_df is not None and not h2h_df.empty:
                # formatação simples
                h2h_fmt = h2h_df.copy()
                for c in h2h_fmt.columns:
                    if c.endswith("%"):
                        h2h_fmt[c] = h2h_fmt[c].map(_pct)
                for c in ["TeamA_gf", "TeamA_ga"]:
                    if c in h2h_fmt.columns:
                        h2h_fmt[c] = h2h_fmt[c].map(_num)

                md_lines = [
                    f"# H2H: {team_a} vs {team_b}" + (f" ({lg_h2h})" if lg_h2h else ""),
                    "",
                    h2h_fmt.to_markdown(index=False),
                    "",
                ]
                safe = f"H2H__{team_a}__vs__{team_b}".replace("/", "_")
                (outdir / f"{safe}.md").write_text("\n".join(md_lines), encoding="utf-8")
                log.info("Relatório H2H gerado: %s", (outdir / f"{safe}.md").resolve())
            else:
                log.warning("Sem jogos suficientes para H2H (%s vs %s).", team_a, team_b)
        else:
            log.warning("--h2h inválido. Use o formato 'Equipa A|Equipa B'.")

    log.info("OK. Ficheiros gerados em: %s", outdir.resolve())
    if len(leagues_found) > 1:
        log.info("Ligas detectadas: %s", ", ".join(leagues_found))
        log.info("Também foram criadas subpastas por liga dentro de: %s", outdir.resolve())


if __name__ == "__main__":
    main()
