# -*- coding: utf-8 -*-
"""
Dashboard Equipas (Streamlit)
- Carrega o relatorio_equipas.xlsx (gerado pelo script analisar_equipas.py)
- Permite filtrar, ver pontos fortes/fracos, explorar mercados e acompanhar forma (rolling)
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import datetime
import matplotlib.pyplot as plt
import plotly.graph_objects as go

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import cm


# ----------------------------
# Config
# ----------------------------
st.set_page_config(page_title="Dashboard Equipas • Multi-liga", layout="wide")

REQUIRED_SHEETS = ["Resumo", "Mercados", "SerieTemporal"]
OPTIONAL_SHEETS = ["Ligas", "Lay_Candidatos", "Lay_Top", "TradingScenarios"]

LEAGUE_NAMES = {
    "E0": "Premier League (Inglaterra)",
    "E1": "Championship (Inglaterra)",
    "F1": "Ligue 1 (França)",
    "I1": "Serie A (Itália)",
    "P1": "Liga Portugal",
    "D1": "Bundesliga",
    "SP1": "La Liga",
    "SC0": "Scottish Premier League",
    "N1": "Eredivisie",
    "T1": "Turkish Superleague",
}



@dataclass(frozen=True)
class MetricSpec:
    col: str
    label: str
    higher_is_better: bool = True
    group: str = "Geral"


METRICS: List[MetricSpec] = [
    MetricSpec("ppg", "Pontos por jogo", True, "Resultados"),
    MetricSpec("vit%", "% Vitórias", True, "Resultados"),
    MetricSpec("emp%", "% Empates", False, "Resultados"),
    MetricSpec("der%", "% Derrotas", False, "Resultados"),
    MetricSpec("golos_marcados", "Golos marcados/jogo", True, "Ataque"),
    MetricSpec("marca%", "% jogos a marcar", True, "Ataque"),
    MetricSpec("remates", "Remates/jogo", True, "Ataque"),
    MetricSpec("SOT", "Remates à baliza/jogo", True, "Ataque"),
    MetricSpec("conversion_rate", "Taxa de conversão (golos/remates)", True, "Ataque"),
    MetricSpec("sot_pct", "SOT% (SOT/remates)", True, "Ataque"),
    MetricSpec("xg_impl", "xG implícito (SOT×0.33) / jogo", True, "Ataque"),
    MetricSpec("cantos", "Cantos/jogo", True, "Ataque"),
    MetricSpec("golos_sofridos", "Golos sofridos/jogo", False, "Defesa"),
    MetricSpec("CS%", "% Clean sheets", True, "Defesa"),
    MetricSpec("remates_sofridos", "Remates sofridos/jogo", False, "Defesa"),
    MetricSpec("SOT_sofridos", "Remates à baliza sofridos/jogo", False, "Defesa"),
    MetricSpec("cantos_sofridos", "Cantos sofridos/jogo", False, "Defesa"),
    MetricSpec("BTTS%", "% BTTS", True, "Ritmo"),
    MetricSpec("O2.5%", "% Over 2.5", True, "Ritmo"),
    MetricSpec("U2.5%", "% Under 2.5", True, "Ritmo"),
    MetricSpec("amarelos", "Amarelos/jogo", False, "Disciplina"),
    MetricSpec("amarelos_sofridos", "Amarelos sofridos/jogo", True, "Disciplina"),
]


PERCENT_COLS = {"vit%", "emp%", "der%", "marca%", "CS%", "BTTS%", "O2.5%", "U2.5%"}


def fmt_pct(x: float) -> str:
    if pd.isna(x):
        return "—"
    return f"{x*100:.1f}%"


def fmt_num(x: float) -> str:
    if pd.isna(x):
        return "—"
    return f"{x:.2f}"


def fmt_roi(x: float) -> str:
    if pd.isna(x):
        return "—"
    return f"{x:+.3f}"


ROLLING_METRICS = {
    "roll5_points": {"kind": "value", "label": "Pontos"},
    "roll5_gf": {"kind": "value", "label": "Golos marcados"},
    "roll5_ga": {"kind": "value", "label": "Golos sofridos"},
    "roll5_goal_diff": {"kind": "value", "label": "Diferença de golos"},
    "roll5_over_2_5": {"kind": "rate", "label": "Over 2.5"},
    "roll5_under_2_5": {"kind": "rate", "label": "Under 2.5"},
    "roll5_btts": {"kind": "rate", "label": "BTTS"},
    "roll5_team_scored": {"kind": "rate", "label": "Equipa marcou"},
    "roll5_clean_sheet": {"kind": "rate", "label": "Clean sheet"},
}


def _pmf(lam: float, k: int) -> float:
    lam = max(float(lam), 1e-9)
    k = int(k)
    if k < 0:
        return 0.0
    return float(math.exp(-lam) * (lam ** k) / math.factorial(k))


def _poisson_pmf_array(lam: float, max_goals: int) -> np.ndarray:
    max_goals = int(max_goals)
    return np.array([_pmf(lam, k) for k in range(max_goals + 1)], dtype=float)


def _looks_cumulative_series(s: pd.Series,
                              corr_threshold: float = 0.92,
                              min_n: int = 6,
                              max_per_game: float = 7.0) -> bool:
    """Detecta se uma série é soma acumulada em vez de valores por jogo.

    O algoritmo anterior (amplitude > 5*std) era matematicamente impossível de satisfazer
    para séries lineares: para qualquer série linear, amplitude/std ≈ 3.46, sempre < 5.0.

    Esta versão usa três critérios combinados:
    1. Monotonia  — >80% dos diffs consecutivos são >= 0 (quase nunca desce)
    2. Correlação — correlação linear com índice > threshold (tendência consistente)
    3. Magnitude  — valor máximo acima do realismo por-jogo (impossível em rolling real)
    """
    s = pd.to_numeric(pd.Series(s).reset_index(drop=True), errors="coerce").dropna()
    if s.size < min_n:
        return False
    diffs = s.diff().dropna()
    if diffs.empty:
        return False
    # 1) Série quase sempre a crescer
    non_decreasing = float((diffs >= -0.01).mean())
    if non_decreasing < 0.80:
        return False
    # 2) Tendência linear forte (correlação com posição no índice)
    idx = np.arange(len(s), dtype=float)
    std_s = float(s.std(ddof=0))
    if std_s < 1e-9:
        return False
    corr = float(np.corrcoef(idx, s.values)[0, 1])
    if corr <= corr_threshold:
        return False
    # 3) Valores impossíveis para métricas por-jogo → definitivamente cumulativo
    #    rolling(5).mean() de golos por jogo nunca excede ~6-7
    return float(s.max()) > max_per_game


def _safe_per_game_series(s: pd.Series) -> pd.Series:
    """Devolve a série com valores por jogo. Se parecer cumulativa, aplica diff()."""
    s_num = pd.to_numeric(pd.Series(s).reset_index(drop=True), errors="coerce")
    if _looks_cumulative_series(s_num):
        s_diff = s_num.diff()
        # Primeiro valor: o próprio (1º jogo da época — acumulado = valor do jogo)
        if len(s_num) > 0 and pd.notna(s_num.iloc[0]):
            s_diff.iloc[0] = s_num.iloc[0]
        return s_diff.fillna(0.0)
    return s_num


def edge_semaforo(edge_media) -> str:
    em = pd.to_numeric(edge_media, errors="coerce")
    if pd.isna(em):
        return "—"
    em = float(em)
    if em > 0.05:
        return "🟢"
    if em >= 0.02:
        return "🟡"
    return "🔴"


def calc_ev_row(r: pd.Series) -> pd.Series:
    p = pd.to_numeric(r.get("p_modelo", np.nan), errors="coerce")
    o = pd.to_numeric(r.get("odds", np.nan), errors="coerce")
    p = float(p) if pd.notna(p) else float("nan")
    o = float(o) if pd.notna(o) else float("nan")
    calc = ev_from_odds(p, o) if pd.notna(o) else {"EV": float("nan"), "fair_odds": float("nan"), "kelly": float("nan")}
    return pd.Series({"fair_odds": calc["fair_odds"], "EV": calc["EV"], "kelly": calc["kelly"]})


def get_team_scope_row(resumo: pd.DataFrame, team: str, scope: str) -> Optional[pd.Series]:
    d = resumo[(resumo["team"] == team) & (resumo["scope"] == scope)]
    if d.empty:
        return None
    return d.iloc[0]


def last_prev_delta(y: np.ndarray):
    y = np.asarray(y, dtype=float)
    idx = np.where(np.isfinite(y))[0]
    if idx.size == 0:
        return np.nan, np.nan, np.nan
    last = float(y[idx[-1]])
    prev = float(y[idx[-2]]) if idx.size >= 2 else np.nan
    delta = last - prev if np.isfinite(prev) else np.nan
    return last, prev, delta


def render_regression_tag_line(label: str, key: str, reg_flags: Dict[str, Dict[str, str]], home_team: str, away_team: str):
    th = reg_flags.get(key, {}).get("home", "")
    ta = reg_flags.get(key, {}).get("away", "")
    if not th and not ta:
        return
    st.markdown(f"**{label}** — {home_team}: {th or '—'} | {away_team}: {ta or '—'}")


def poisson_prob_for_market(mkt: str, probs: Dict[str, float]) -> float:
    m = str(mkt).lower()
    if "over 2.5" in m:
        return float(probs.get("Over 2.5", np.nan))
    if "over 1.5" in m:
        return float(probs.get("Over 1.5", np.nan))
    if "under 2.5" in m:
        return float(probs.get("Under 2.5", np.nan))
    if "under 3.5" in m:
        return float(probs.get("Under 3.5", np.nan))
    if "btts" in m or "ambas" in m:
        return float(probs.get("BTTS Sim", np.nan))
    if "casa marca" in m:
        return float(probs.get("Casa marca (>=1)", np.nan))
    if "fora marca" in m:
        return float(probs.get("Fora marca (>=1)", np.nan))
    return float("nan")


def shortlist_signal_row(r: pd.Series) -> str:
    em = pd.to_numeric(r.get("edge_media", np.nan), errors="coerce")
    pp = pd.to_numeric(r.get("p_poisson", np.nan), errors="coerce")
    vv = pd.to_numeric(r.get("value_est_media", np.nan), errors="coerce")
    cond_edge = pd.notna(em) and em > 0.03
    cond_pois = pd.notna(pp) and pp >= 0.50
    cond_val = True if pd.isna(vv) else (vv > 0)
    return "✅" if (cond_edge and cond_pois and cond_val) else ""


def pnl_row(r: pd.Series) -> float:
    st_u = pd.to_numeric(r.get("stake_u"), errors="coerce")
    od = pd.to_numeric(r.get("odds"), errors="coerce")
    if pd.isna(st_u) or pd.isna(od):
        return float("nan")
    estado = str(r.get("estado", "pendente")).lower()
    if estado == "ganhou":
        return float(st_u * (od - 1.0))
    if estado == "perdeu":
        return float(-st_u)
    return 0.0


def plot_line_series_interactive(x, series_map: Dict[str, np.ndarray], title: str, xlabel: str, ylabel: str, is_pct: bool = False):
    x_vals = pd.Series(x).reset_index(drop=True).tolist()
    fig = go.Figure()

    for label, y in series_map.items():
        y_ser = pd.to_numeric(pd.Series(y).reset_index(drop=True), errors="coerce")

        n = min(len(x_vals), len(y_ser))
        if n == 0:
            continue

        x_plot = x_vals[:n]
        y_arr = y_ser.iloc[:n].to_numpy(dtype=float)

        if is_pct:
            finite = y_arr[np.isfinite(y_arr)]
            if finite.size and np.nanmax(np.abs(finite)) <= 1.0 + 1e-9:
                y_arr = y_arr * 100.0

        fig.add_trace(
            go.Scatter(
                x=x_plot,
                y=y_arr,
                mode="lines+markers",
                name=label,
                connectgaps=False,
            )
        )

        idx = np.where(np.isfinite(y_arr))[0]
        if idx.size:
            i = int(idx[-1])
            x_last = x_plot[i]
            y_last = float(y_arr[i])
            fig.add_annotation(
                x=x_last,
                y=y_last,
                text=(f"{y_last:.0f}%" if is_pct else f"{y_last:.2f}"),
                showarrow=False,
                xanchor="left",
                yanchor="middle",
                xshift=10,
            )

    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        hovermode="x unified",
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    if is_pct:
        fig.update_yaxes(range=[0, 100], ticksuffix="%")

    st.plotly_chart(fig, use_container_width=True)




def _to_prob(p) -> float:
    """Normaliza uma taxa/probabilidade para [0,1]. Aceita valores em [0,1] ou em percentagem [0,100]."""
    p = pd.to_numeric(p, errors="coerce")
    if pd.isna(p):
        return float("nan")
    p = float(p)
    if p > 1.0:
        p = p / 100.0
    # clamp
    if p < 0.0:
        p = 0.0
    if p > 1.0:
        p = 1.0
    return p


def fair_odds_from_hit_rate(hit_rate) -> float:
    p = _to_prob(hit_rate)
    if pd.isna(p) or p <= 0:
        return float("nan")
    return 1.0 / p


def value_estimado(hit_rate, odds_avg) -> float:
    """Value estimado: value = hit_rate / (1/odds) - 1. Devolve em escala [-1..+inf)."""
    p = _to_prob(hit_rate)
    o = pd.to_numeric(odds_avg, errors="coerce")
    if pd.isna(p) or pd.isna(o) or o <= 0:
        return float("nan")
    o = float(o)
    return p / (1.0 / o) - 1.0  # equivalente a p*o - 1


def wilson_ci(hit_rate, n, z: float = 1.645) -> Tuple[float, float]:
    """Intervalo de confiança de Wilson para proporções (por defeito 90%)."""
    p = _to_prob(hit_rate)
    nn = pd.to_numeric(n, errors="coerce")
    if pd.isna(p) or pd.isna(nn) or nn <= 0:
        return (float("nan"), float("nan"))
    nn = float(nn)

    denom = 1.0 + (z ** 2) / nn
    centre = (p + (z ** 2) / (2.0 * nn)) / denom
    margin = (z * math.sqrt((p * (1.0 - p) / nn) + (z ** 2) / (4.0 * nn ** 2))) / denom
    lo = max(0.0, centre - margin)
    hi = min(1.0, centre + margin)
    return (lo, hi)


def _style_value_series(s: pd.Series):
    """Styler.apply para 'value_est' (verde para >0, vermelho para <0). Aceita numérico ou string (ex.: '+12.3%')."""
    out = []
    for v in s:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            out.append("")
            continue
        vv = None
        if isinstance(v, str):
            vv_str = v.strip().replace("%", "").replace("pp", "").replace(",", ".")
            try:
                vv = float(vv_str)
                # se vier em percentagem (ex.: 12.3), converte para 0.123 só para consistência; o sinal é o que importa
                if abs(vv) > 1.5:
                    vv = vv / 100.0
            except Exception:
                vv = None
        else:
            try:
                vv = float(v)
            except Exception:
                vv = None

        if vv is None or (isinstance(vv, float) and np.isnan(vv)):
            out.append("")
        elif vv > 0:
            out.append("background-color: rgba(0, 200, 0, 0.18); color: #0b3d0b; font-weight: 600;")
        elif vv < 0:
            out.append("background-color: rgba(220, 0, 0, 0.16); color: #4a0b0b; font-weight: 600;")
        else:
            out.append("")
    return out

def _safe_float(x, default=float("nan")) -> float:
    """Converte para float de forma segura (evita None, '—', Ellipsis, etc.)."""
    try:
        if x is None or x is ...:
            return default
        # strings tipo "—" ou vazias
        if isinstance(x, str):
            x = x.strip()
            if x in {"", "—", "-"}:
                return default
        return float(x)
    except Exception:
        return default

def build_prejogo_pdf(
    league_label_txt: str,
    home_team: str,
    away_team: str,
    settings: dict,
    eg_home: float,
    eg_away: float,
    probs_table: pd.DataFrame,
    conf: dict,
    matchup_tables: dict | None = None,
    shortlist_df: pd.DataFrame | None = None,
    suggestions: list[str] | None = None,
    context_notes: str = "",
    context_meta: dict | None = None,
) -> bytes:
    """
    Gera um PDF (bytes) com o resumo da análise Pré-jogo.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.0*cm,
        rightMargin=2.0*cm,
        topMargin=1.8*cm,
        bottomMargin=1.8*cm,
        title="Pré-jogo",
        author="Dashboard Equipas",
    )
    styles = getSampleStyleSheet()
    story = []

    title = f"Pré-jogo • {league_label_txt} — {home_team} vs {away_team}"
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 8))

    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(f"<b>Gerado:</b> {ts}", styles["Normal"]))
    story.append(Paragraph(
        f"<b>Definições:</b> peso_forma={settings.get('peso_forma', '—')}% | "
        f"últimosN={settings.get('recent_n', '—')} | "
        f"min_jogos={settings.get('min_games', '—')} | "
        f"threshold_prob={settings.get('prob_threshold', '—')} | "
        f"peso_PPG={settings.get('alpha_ppg', '—')}%",
        styles["Normal"]
    ))
    story.append(Spacer(1, 10))

    # Notas de contexto (qualitativo)
    notes_txt = str(context_notes).strip() if context_notes is not None else ""
    if notes_txt:
        story.append(Paragraph("<b>Notas de contexto</b>", styles["Heading2"]))
        story.append(Paragraph(notes_txt.replace("\n", "<br/>"), styles["BodyText"]))
        story.append(Spacer(1, 10))

    # Contexto de tabela / importância (opcional)
    if context_meta:
        try:
            ph = context_meta.get("pos_home", "—")
            pa = context_meta.get("pos_away", "—")
            pth = context_meta.get("pts_home", "—")
            pta = context_meta.get("pts_away", "—")
            imp_h = context_meta.get("imp_home", "—")
            imp_a = context_meta.get("imp_away", "—")
            story.append(Paragraph("<b>Contexto de tabela e pressão</b>", styles["Heading2"]))
            story.append(Paragraph(f"Posição/Pontos — Casa: <b>{ph}</b> / <b>{pth}</b> | Fora: <b>{pa}</b> / <b>{pta}</b>", styles["Normal"]))
            story.append(Paragraph(f"Importância do jogo (1-10) — Casa: <b>{imp_h}</b> | Fora: <b>{imp_a}</b>", styles["Normal"]))
            story.append(Spacer(1, 10))
        except Exception:
            pass

    story.append(Paragraph("<b>1) EG (Expected Goals) e probabilidades (modelo Poisson simples)</b>", styles["Heading2"]))

    eh = _safe_float(eg_home)
    ea = _safe_float(eg_away)
    story.append(Paragraph(f"EG Casa: <b>{eh:.2f}</b> | EG Fora: <b>{ea:.2f}</b>", styles["Normal"]))
    story.append(Spacer(1, 6))

    pt = probs_table.copy()
    data = [pt.columns.tolist()] + pt.values.tolist()
    table = Table(data, colWidths=[8.5*cm, 4.0*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 10),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONTSIZE", (0,1), (-1,-1), 9),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>2) Indicador de confiança (amostra + estabilidade)</b>", styles["Heading2"]))
    conf_score = _safe_float(conf.get("conf_score"))
    factor_amostra = _safe_float(conf.get("factor_amostra"))
    factor_est = _safe_float(conf.get("factor_estabilidade"))
    jogos_casa = int(_safe_float(conf.get("jogos_casa"), 0))
    jogos_fora = int(_safe_float(conf.get("jogos_fora"), 0))
    
    story.append(Paragraph(
        f"Confiança (0-100): <b>{conf_score:.0f}</b> | "
        f"Factor amostra: <b>{factor_amostra:.2f}</b> | "
        f"Factor estabilidade: <b>{factor_est:.2f}</b> | "
        f"Jogos (Casa/Fora): <b>{jogos_casa}/{jogos_fora}</b>",
        styles["Normal"]))
    story.append(Spacer(1, 10))
    
    # 2b) Pontos fortes/fracos do matchup (Casa vs Fora)
    if matchup_tables:
            story.append(Paragraph("<b>2b) Pontos fortes / fracos do matchup (Casa vs Fora)</b>", styles["Heading2"]))
            story.append(Spacer(1, 6))
        
            def _fmt_val(col: str, v):
                if pd.isna(v):
                    return "—"
                # percentagens
                if col in {"vit%", "emp%", "der%", "marca%", "CS%", "BTTS%", "O2.5%", "U2.5%"}:
                    return f"{float(v)*100:.1f}%"
                return f"{float(v):.2f}"
        
            def _mini_table(df: pd.DataFrame, title: str):
                if df is None or df.empty:
                    story.append(Paragraph(f"{title}: —", styles["Normal"]))
                    story.append(Spacer(1, 4))
                    return
        
                # esperamos colunas: grupo, métrica, col, valor, z
                t = df.copy()
                # garantir colunas
                for c in ["grupo", "métrica", "col", "valor", "z"]:
                    if c not in t.columns:
                        t[c] = ""
        
                # top 5
                t = t.head(5)
        
                data = [["Grupo", "Métrica", "Valor", "z"]]
                for _, r in t.iterrows():
                    data.append([
                        str(r["grupo"]),
                        str(r["métrica"]),
                        _fmt_val(str(r["col"]), r["valor"]),
                        f"{float(r['z']):+.2f}" if pd.notna(r["z"]) else "—",
                    ])
        
                story.append(Paragraph(title, styles["Heading3"]))
                tbl = Table(data, colWidths=[3.0*cm, 8.2*cm, 2.4*cm, 1.2*cm])
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
                    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                    ("FONTSIZE", (0,0), (-1,0), 9),
                    ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
                    ("FONTSIZE", (0,1), (-1,-1), 8),
                    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 8))
        
            _mini_table(matchup_tables.get("home_strengths"), f"{home_team} (Casa) — Forças vs liga (Casa)")
            _mini_table(matchup_tables.get("home_weaknesses"), f"{home_team} (Casa) — Fraquezas vs liga (Casa)")
            _mini_table(matchup_tables.get("away_strengths"), f"{away_team} (Fora) — Forças vs liga (Fora)")
            _mini_table(matchup_tables.get("away_weaknesses"), f"{away_team} (Fora) — Fraquezas vs liga (Fora)")
        
            if shortlist_df is not None and not shortlist_df.empty:
                story.append(Paragraph("<b>3) Shortlist de mercados (edge histórico Casa + Fora)</b>", styles["Heading2"]))
                top = shortlist_df.head(10).copy()
        
                for c in ["edge_media", "edge_vs_liga_casa", "edge_vs_liga_fora"]:
                    if c in top.columns:
                        top[c] = top[c].apply(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f} pp")
        
                data2 = [["Mercado", "Edge média", "Edge casa", "Edge fora", "Jogos casa", "Jogos fora"]]
                for _, r in top.iterrows():
                    data2.append([
                        str(r.get("market","")),
                        str(r.get("edge_media","")),
                        str(r.get("edge_vs_liga_casa","")),
                        str(r.get("edge_vs_liga_fora","")),
                        str(int(r.get("jogos_casa",0))),
                        str(int(r.get("jogos_fora",0))),
                    ])
        
                table2 = Table(data2, colWidths=[6.2*cm, 2.1*cm, 2.1*cm, 2.1*cm, 2.0*cm, 2.0*cm])
                table2.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
                    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                    ("FONTSIZE", (0,0), (-1,0), 9),
                    ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
                    ("FONTSIZE", (0,1), (-1,-1), 8),
                    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
                ]))
                story.append(table2)
                story.append(Spacer(1, 10))
        
            if suggestions:
                story.append(Paragraph("<b>4) Sugestões / ângulos</b>", styles["Heading2"]))
                for item in suggestions[:12]:
                    story.append(Paragraph(str(item).lstrip("• ").replace("**",""), styles["Normal"]))
                story.append(Spacer(1, 8))
        
    story.append(Paragraph("<i>Nota:</i> análise descritiva/heurística baseada em histórico. Usar sempre contexto.", styles["Normal"]))
    doc.build(story)
    return buf.getvalue()


@st.cache_data(show_spinner=False)
def load_report(uploaded: Optional[io.BytesIO], fallback_path: str = "relatorio_equipas.xlsx") -> Dict[str, pd.DataFrame]:
    """
    Carrega o relatório. Se não houver upload, tenta ler do path local.
    """
    if uploaded is None:
        try:
            xl = pd.ExcelFile(fallback_path)
        except Exception as e:
            raise RuntimeError(
                f"Não foi possível ler '{fallback_path}'. Faz upload do ficheiro ou coloca-o na mesma pasta do app.\n\nDetalhe: {e}"
            )
    else:
        xl = pd.ExcelFile(uploaded)

    missing = [s for s in REQUIRED_SHEETS if s not in xl.sheet_names]
    if missing:
        raise RuntimeError(f"O ficheiro não tem as folhas esperadas: {missing}. Encontrei: {xl.sheet_names}")

    dfs = {name: xl.parse(name) for name in REQUIRED_SHEETS}
    for opt in OPTIONAL_SHEETS:
        if opt in xl.sheet_names:
            dfs[opt] = xl.parse(opt)

    # Normalizar coluna de liga
    for k, d in list(dfs.items()):
        if "league" not in d.columns:
            if "Div" in d.columns:
                dfs[k] = d.rename(columns={"Div": "league"})
            elif "League" in d.columns:
                dfs[k] = d.rename(columns={"League": "league"})
            else:
                dfs[k] = d.copy()
                dfs[k]["league"] = "ALL"


    # Tipos e limpeza leve
    if "scope" in dfs["Resumo"].columns:
        dfs["Resumo"]["scope"] = dfs["Resumo"]["scope"].astype(str)
    dfs["Mercados"]["scope"] = dfs["Mercados"]["scope"].astype(str)
    dfs["Mercados"]["market"] = dfs["Mercados"]["market"].astype(str)
    dfs["Resumo"]["league"] = dfs["Resumo"]["league"].astype(str)
    dfs["Mercados"]["league"] = dfs["Mercados"]["league"].astype(str)
    dfs["SerieTemporal"]["league"] = dfs["SerieTemporal"]["league"].astype(str)
    dfs["SerieTemporal"]["venue"] = dfs["SerieTemporal"]["venue"].astype(str)

    # Normalizar venue para "H"/"A" independentemente do valor original no Excel.
    # Suporta: "H"/"A", "Home"/"Away", "1"/"0", "Casa"/"Fora", "h"/"a", etc.
    _venue_raw = dfs["SerieTemporal"]["venue"].str.strip().str.upper()
    _home_mask = _venue_raw.isin(["H", "HOME", "CASA", "1"])
    _away_mask = _venue_raw.isin(["A", "AWAY", "FORA", "0", "2"])
    dfs["SerieTemporal"]["venue"] = np.where(
        _home_mask, "H", np.where(_away_mask, "A", dfs["SerieTemporal"]["venue"])
    )

    # Garantir datetime
    if not np.issubdtype(dfs["SerieTemporal"]["date"].dtype, np.datetime64):
        dfs["SerieTemporal"]["date"] = pd.to_datetime(dfs["SerieTemporal"]["date"], errors="coerce")

    # Trading Lay (opcional): normalizar tipos se as sheets existirem
    for k in ["Lay_Candidatos", "Lay_Top", "TradingScenarios"]:
        if k in dfs:
            d = dfs[k].copy()
            if "league" in d.columns:
                d["league"] = d["league"].astype(str)
            for c in ["team", "scope", "cenario_lay", "descricao"]:
                if c in d.columns:
                    d[c] = d[c].astype(str)
            if "flag_candidato" in d.columns:
                d["flag_candidato"] = d["flag_candidato"].fillna(False).astype(bool)
            # numéricos (quando existirem)
            for c in ["jogos", "hit_rate", "wilson_lo", "wilson_hi", "edge_vs_liga", "lay_score", "confidence_weight"]:
                if c in d.columns:
                    d[c] = pd.to_numeric(d[c], errors="coerce")
            dfs[k] = d
    return dfs


def compute_league_means(resumo: pd.DataFrame) -> pd.DataFrame:
    cols = [m.col for m in METRICS if m.col in resumo.columns]
    out = resumo.groupby("scope", as_index=False)[cols].mean(numeric_only=True)
    out.insert(0, "team", "Média Liga")
    return out

def weighted_mean(df: pd.DataFrame, value_col: str, weight_col: str) -> float:
    v = pd.to_numeric(df[value_col], errors="coerce")
    w = pd.to_numeric(df[weight_col], errors="coerce")
    m = (~v.isna()) & (~w.isna()) & (w > 0)
    if not m.any():
        return float("nan")
    return float((v[m] * w[m]).sum() / w[m].sum())


@st.cache_data(show_spinner=False)
def league_reference(resumo: pd.DataFrame) -> Dict[str, float]:
    """
    Médias ponderadas (por número de jogos) para normalização.
    """
    ref = {}
    for scope in ["Total", "Casa", "Fora"]:
        d = resumo[resumo["scope"] == scope].copy()
        if d.empty:
            continue
        for col in ["golos_marcados", "golos_sofridos", "ppg", "SOT", "SOT_sofridos", "cantos", "cantos_sofridos"]:
            if col in d.columns:
                ref[f"{scope}:{col}"] = weighted_mean(d, col, "jogos")
    return ref

def team_strength_scores(resumo: pd.DataFrame, alpha_ppg: float = 0.6) -> Dict[str, float]:
    """
    Força global por equipa (na liga seleccionada), baseada em:
      strength = alpha*Z(PPG_total) + (1-alpha)*Z(diff_golos_total)

    - alpha_ppg: 0..1 (peso do PPG)
    Retorna dict team -> strength (média ~0, pode ser negativo/positivo).
    """
    alpha_ppg = float(np.clip(alpha_ppg, 0.0, 1.0))
    d = resumo[resumo["scope"] == "Total"].copy()
    if d.empty:
        return {}

    d["ppg"] = pd.to_numeric(d.get("ppg"), errors="coerce")
    if "diff_golos" in d.columns:
        d["diff_golos"] = pd.to_numeric(d.get("diff_golos"), errors="coerce")
    else:
        d["diff_golos"] = np.nan

    def z(series: pd.Series) -> pd.Series:
        mu = series.mean(skipna=True)
        sd = series.std(ddof=0, skipna=True)
        if pd.isna(sd) or sd == 0:
            return series * 0.0
        return (series - mu) / sd

    z_ppg = z(d["ppg"])
    z_dg = z(d["diff_golos"])

    strength = alpha_ppg * z_ppg + (1.0 - alpha_ppg) * z_dg
    return dict(zip(d["team"].astype(str), strength.fillna(0.0).astype(float)))    

def poisson_probs(lam_home: float, lam_away: float, max_goals: int = 10) -> Dict[str, float]:
    """
    Probabilidades básicas usando Poisson independente (heurística).
    """
    lam_home = max(float(lam_home), 1e-9)
    lam_away = max(float(lam_away), 1e-9)

    ph = _poisson_pmf_array(lam_home, max_goals)
    pa = _poisson_pmf_array(lam_away, max_goals)

    # joint
    P = np.outer(ph, pa)
    # outcomes
    home_win = float(np.tril(P, -1).sum())
    draw = float(np.trace(P))
    away_win = float(np.triu(P, 1).sum())

    # totals
    totals = np.array([P[i, j] for i in range(max_goals + 1) for j in range(max_goals + 1)])
    # easier: compute distribution of total goals
    total_dist = np.zeros(2 * max_goals + 1)
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            total_dist[i + j] += P[i, j]

    over_25 = float(total_dist[3:].sum())
    under_25 = float(total_dist[:3].sum())
    over_15 = float(total_dist[2:].sum())
    under_35 = float(total_dist[:4].sum())

    btts = float(P[1:, 1:].sum())
    home_scores = float(1 - ph[0])
    away_scores = float(1 - pa[0])

    return {
        "EG Casa": lam_home,
        "EG Fora": lam_away,
        "1 (Casa vence)": home_win,
        "X (Empate)": draw,
        "2 (Fora vence)": away_win,
        "Over 1.5": over_15,
        "Over 2.5": over_25,
        "Under 2.5": under_25,
        "Under 3.5": under_35,
        "BTTS Sim": btts,
        "Casa marca (>=1)": home_scores,
        "Fora marca (>=1)": away_scores,
    }

def poisson_score_matrix(lam_home: float, lam_away: float, max_goals: int = 5) -> pd.DataFrame:
    """Matriz de probabilidades (scorelines) 0..max_goals para Casa x Fora."""
    lam_home = max(float(lam_home), 1e-9)
    lam_away = max(float(lam_away), 1e-9)

    def pmf(lam: float, k: int) -> float:
        return math.exp(-lam) * (lam ** k) / math.factorial(k)

    ph = np.array([pmf(lam_home, k) for k in range(max_goals + 1)], dtype=float)
    pa = np.array([pmf(lam_away, k) for k in range(max_goals + 1)], dtype=float)
    P = np.outer(ph, pa)

    df = pd.DataFrame(
        P,
        index=[str(i) for i in range(max_goals + 1)],
        columns=[str(j) for j in range(max_goals + 1)],
    )
    df.index.name = "Casa\\Fora"
    return df




def asian_handicap_table(score_matrix: pd.DataFrame) -> pd.DataFrame:
    """
    Probabilidades (ganha / push / perde) para algumas linhas de Handicap Asiático,
    a partir de uma matriz de scorelines (Casa x Fora).

    Nota: a matriz é truncada (0..max_goals). A massa de probabilidade fora do intervalo é ignorada.
    """
    if score_matrix is None or score_matrix.empty:
        return pd.DataFrame()

    M = score_matrix.to_numpy(dtype=float)
    n_h, n_a = M.shape
    ih = np.arange(n_h)[:, None]
    ia = np.arange(n_a)[None, :]
    diff = ih - ia  # home - away

    lines = [
        ("Casa -0.5", -0.5),
        ("Casa -1.0", -1.0),
        ("Casa -1.5", -1.5),
        ("Casa -2.0", -2.0),
        ("Fora +0.5", +0.5),
        ("Fora +1.0", +1.0),
        ("Fora +1.5", +1.5),
        ("Fora +2.0", +2.0),
    ]

    rows = []
    for label, h in lines:
        # Interpretamos 'h' como handicap aplicado à equipa escolhida no label
        # - Casa -1.0: ganha se diff >= 2, push se diff == 1, perde caso contrário
        # - Fora +1.0: ganha se diff <= 0, push se diff == 1, perde se diff >= 2
        push = 0.0

        if "Casa" in label:
            # handicap negativo ou meio
            if float(h).is_integer():  # linha inteira (-1.0, -2.0)
                k = int(abs(h))
                p_win = float(M[diff >= (k + 1)].sum())
                p_push = float(M[diff == k].sum())
                p_lose = float(M[diff <= (k - 1)].sum())
                push = p_push
            else:  # meia linha (-0.5, -1.5, ...)
                # Casa -0.5: diff >= 1
                thr = int(math.floor(abs(h) + 0.5))  # -0.5 -> 1; -1.5 -> 2
                p_win = float(M[diff >= thr].sum())
                p_lose = float(1.0 - p_win)
                p_push = 0.0
        else:
            # handicap positivo para Fora
            if float(h).is_integer():  # +1.0, +2.0
                k = int(abs(h))
                p_win = float(M[diff <= (k - 1)].sum())
                p_push = float(M[diff == k].sum())
                p_lose = float(M[diff >= (k + 1)].sum())
                push = p_push
            else:  # +0.5, +1.5 ...
                thr = int(math.floor(abs(h) - 0.5))  # +0.5 -> 0; +1.5 -> 1
                p_win = float(M[diff <= thr].sum())
                p_lose = float(1.0 - p_win)
                p_push = 0.0

        # fair odds (break-even) considerando push (quando existe):
        # EV=0 -> odds = 1 + p_lose/p_win = (1 - p_push)/p_win
        fair = float("nan")
        if p_win > 0:
            fair = (1.0 - p_push) / p_win

        rows.append({
            "Linha": label,
            "P(gana)": p_win,
            "P(push)": p_push,
            "P(perde)": p_lose,
            "Fair odds": fair,
        })

    df = pd.DataFrame(rows)
    return df
# ----------------------------
# Helpers adicionais (HT, cantos/cartões, regressão, forma comparada)
# ----------------------------

def ensure_ht_columns(serie: pd.DataFrame) -> Tuple[pd.DataFrame, bool]:
    """Garante colunas `ht_gf` e `ht_ga` (golos ao intervalo) se existirem dados.
    Suporta:
    - colunas directas ht_gf/ht_ga
    - colunas de jogo HTHG/HTAG (ou hthg/htag) + colunas team/home_team/away_team
    """
    if {"ht_gf", "ht_ga"}.issubset(set(serie.columns)):
        return serie, True

    if not {"team", "home_team", "away_team"}.issubset(set(serie.columns)):
        return serie, False

    candidates = [
        ("HTHG", "HTAG"),
        ("hthg", "htag"),
        ("HTH", "HTA"),
    ]
    for hcol, acol in candidates:
        if hcol in serie.columns and acol in serie.columns:
            s = serie.copy()
            is_home = (s["team"] == s["home_team"])
            is_away = (s["team"] == s["away_team"])
            s["ht_gf"] = np.where(is_home, pd.to_numeric(s[hcol], errors="coerce"),
                                  np.where(is_away, pd.to_numeric(s[acol], errors="coerce"), np.nan))
            s["ht_ga"] = np.where(is_home, pd.to_numeric(s[acol], errors="coerce"),
                                  np.where(is_away, pd.to_numeric(s[hcol], errors="coerce"), np.nan))
            # venue se faltar
            if "venue" not in s.columns:
                s["venue"] = np.where(is_home, "H", np.where(is_away, "A", ""))
            return s, True

    return serie, False


def expected_goals_ht(
    serie: pd.DataFrame,
    home_team: str,
    away_team: str,
    weight_recent: float = 0.35,
    recent_n: int = 5,
) -> Tuple[float, float, Dict[str, float]]:
    """EG ao intervalo (HT) com a mesma lógica multiplicativa do EG FT.
    Usa apenas `SerieTemporal` (precisa de `ht_gf`/`ht_ga`).
    """
    # liga (baselines)
    league_home_ht_gf = float(pd.to_numeric(serie.loc[serie["venue"] == "H", "ht_gf"], errors="coerce").mean())
    league_home_ht_ga = float(pd.to_numeric(serie.loc[serie["venue"] == "H", "ht_ga"], errors="coerce").mean())
    league_away_ht_gf = float(pd.to_numeric(serie.loc[serie["venue"] == "A", "ht_gf"], errors="coerce").mean())
    league_away_ht_ga = float(pd.to_numeric(serie.loc[serie["venue"] == "A", "ht_ga"], errors="coerce").mean())

    def _team_rates(team: str, venue: str) -> Tuple[float, float, float, float]:
        d = serie[(serie["team"] == team) & (serie["venue"] == venue)].sort_values("date").copy()
        d["ht_gf"] = pd.to_numeric(d["ht_gf"], errors="coerce")
        d["ht_ga"] = pd.to_numeric(d["ht_ga"], errors="coerce")
        d = d.dropna(subset=["ht_gf", "ht_ga"])
        if d.empty:
            return float("nan"), float("nan"), float("nan"), float("nan")
        season_gf = float(d["ht_gf"].mean())
        season_ga = float(d["ht_ga"].mean())
        tail = d.tail(int(recent_n))
        recent_gf = float(tail["ht_gf"].mean())
        recent_ga = float(tail["ht_ga"].mean())
        return season_gf, season_ga, recent_gf, recent_ga

    def mix(season_val: float, recent_val: float) -> float:
        if (not np.isnan(season_val)) and (not np.isnan(recent_val)):
            return (1 - weight_recent) * season_val + weight_recent * recent_val
        if not np.isnan(season_val):
            return season_val
        if not np.isnan(recent_val):
            return recent_val
        return float("nan")

    h_se_gf, h_se_ga, h_re_gf, h_re_ga = _team_rates(home_team, "H")
    a_se_gf, a_se_ga, a_re_gf, a_re_ga = _team_rates(away_team, "A")

    h_gf = mix(h_se_gf, h_re_gf)
    h_ga = mix(h_se_ga, h_re_ga)
    a_gf = mix(a_se_gf, a_re_gf)
    a_ga = mix(a_se_ga, a_re_ga)

    # multiplicadores
    home_att = h_gf / league_home_ht_gf if league_home_ht_gf and not np.isnan(league_home_ht_gf) else np.nan
    home_def_weak = h_ga / league_home_ht_ga if league_home_ht_ga and not np.isnan(league_home_ht_ga) else np.nan
    away_att = a_gf / league_away_ht_gf if league_away_ht_gf and not np.isnan(league_away_ht_gf) else np.nan
    away_def_weak = a_ga / league_away_ht_ga if league_away_ht_ga and not np.isnan(league_away_ht_ga) else np.nan

    eg_ht_home = (league_home_ht_gf * home_att * away_def_weak) if all([not np.isnan(x) for x in [league_home_ht_gf, home_att, away_def_weak]]) else np.nan
    eg_ht_away = (league_away_ht_gf * away_att * home_def_weak) if all([not np.isnan(x) for x in [league_away_ht_gf, away_att, home_def_weak]]) else np.nan

    dbg = {
        "league_home_ht_gf": league_home_ht_gf,
        "league_away_ht_gf": league_away_ht_gf,
        "home_ht_gf_season": h_se_gf,
        "home_ht_ga_season": h_se_ga,
        "away_ht_gf_season": a_se_gf,
        "away_ht_ga_season": a_se_ga,
        "home_ht_gf_recent": h_re_gf,
        "home_ht_ga_recent": h_re_ga,
        "away_ht_gf_recent": a_re_gf,
        "away_ht_ga_recent": a_re_ga,
        "weight_recent": weight_recent,
    }
    return float(eg_ht_home), float(eg_ht_away), dbg


def poisson_over_prob(lam_total: float, line: float, max_k: int = 40) -> float:
    """P(Total > line) para Poisson(λ). lines típicas: 8.5, 9.5, etc."""
    if not np.isfinite(lam_total) or lam_total < 0:
        return float("nan")
    k = int(math.floor(line))
    lam_total = max(float(lam_total), 1e-9)

    # CDF até k
    cdf = 0.0
    for i in range(0, min(k, max_k) + 1):
        cdf += math.exp(-lam_total) * (lam_total ** i) / math.factorial(i)
    return float(max(0.0, min(1.0, 1.0 - cdf)))


def expected_count_match(
    resumo: pd.DataFrame,
    home_team: str,
    away_team: str,
    metric_for: str,
    metric_against: str,
) -> Tuple[float, float, Dict[str, float]]:
    """Modelo multiplicativo tipo EG, mas para contagens (cantos/cartões).
    metric_for: ex. 'cantos' (a favor) | metric_against: ex. 'cantos_sofridos' (contra)
    """
    ref = league_reference(resumo)
    home_row = get_team_scope_row(resumo, home_team, "Casa")
    away_row = get_team_scope_row(resumo, away_team, "Fora")
    if home_row is None or away_row is None:
        return float("nan"), float("nan"), {}

    h_for = float(pd.to_numeric(home_row.get(metric_for, np.nan), errors="coerce"))
    h_against = float(pd.to_numeric(home_row.get(metric_against, np.nan), errors="coerce"))
    a_for = float(pd.to_numeric(away_row.get(metric_for, np.nan), errors="coerce"))
    a_against = float(pd.to_numeric(away_row.get(metric_against, np.nan), errors="coerce"))

    league_h_for = float(ref.get(f"Casa:{metric_for}", np.nan))
    league_h_against = float(ref.get(f"Casa:{metric_against}", np.nan))
    league_a_for = float(ref.get(f"Fora:{metric_for}", np.nan))
    league_a_against = float(ref.get(f"Fora:{metric_against}", np.nan))

    h_att = h_for / league_h_for if league_h_for and not np.isnan(league_h_for) else np.nan
    h_def_weak = h_against / league_h_against if league_h_against and not np.isnan(league_h_against) else np.nan
    a_att = a_for / league_a_for if league_a_for and not np.isnan(league_a_for) else np.nan
    a_def_weak = a_against / league_a_against if league_a_against and not np.isnan(league_a_against) else np.nan

    lam_home = (league_h_for * h_att * a_def_weak) if all([not np.isnan(x) for x in [league_h_for, h_att, a_def_weak]]) else np.nan
    lam_away = (league_a_for * a_att * h_def_weak) if all([not np.isnan(x) for x in [league_a_for, a_att, h_def_weak]]) else np.nan

    dbg = {
        "home_for": h_for, "home_against": h_against,
        "away_for": a_for, "away_against": a_against,
        "league_home_for": league_h_for, "league_away_for": league_a_for,
    }
    return float(lam_home), float(lam_away), dbg


def regression_flag(values: pd.Series, last_n: int = 5, k: float = 1.5) -> Tuple[str, float, float, float]:
    """Compara média dos últimos N com média/STD da época.
    Devolve (tag, recent_mean, season_mean, season_std)
    """
    v = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if v.shape[0] < max(6, last_n):
        return "", float("nan"), float("nan"), float("nan")
    season_mean = float(v.mean())
    season_std = float(v.std(ddof=0))
    recent_mean = float(v.tail(int(last_n)).mean())
    if not np.isfinite(season_std) or season_std <= 1e-12:
        return "", recent_mean, season_mean, season_std
    if recent_mean > season_mean + k * season_std:
        return "⚡ Alta (risco de regressão)", recent_mean, season_mean, season_std
    if recent_mean < season_mean - k * season_std:
        return "📉 Baixa (potencial recuperação)", recent_mean, season_mean, season_std
    return "", recent_mean, season_mean, season_std


def indicator_series(serie: pd.DataFrame, team: str, venue: str, kind: str) -> pd.Series:
    """Série 1D (ordenada por data) para um indicador no contexto (H/A)."""
    d = serie[(serie["team"] == team) & (serie["venue"] == venue)].sort_values("date").copy()
    if d.empty:
        return pd.Series(dtype=float)
    gf = _safe_per_game_series(d.get("gf", np.nan))
    ga = _safe_per_game_series(d.get("ga", np.nan))
    if kind == "over25":
        return ((gf + ga) >= 3).astype(float)
    if kind == "btts":
        return ((gf >= 1) & (ga >= 1)).astype(float)
    if kind == "scored":
        return (gf >= 1).astype(float)
    if kind == "total_goals":
        return (gf + ga).astype(float)
    if kind == "gf":
        return gf.astype(float)
    if kind == "ga":
        return ga.astype(float)
    return pd.Series(dtype=float)


@st.cache_data(show_spinner=False)
def matchup_regression_flags(serie: pd.DataFrame, home_team: str, away_team: str, last_n: int = 5, k: float = 1.5) -> Dict[str, Dict[str, str]]:
    """Flags de regressão por indicador (casa vs fora)."""
    out: Dict[str, Dict[str, str]] = {}
    for kind in ["over25", "btts", "scored", "total_goals"]:
        s_h = indicator_series(serie, home_team, "H", kind)
        s_a = indicator_series(serie, away_team, "A", kind)
        tag_h, *_ = regression_flag(s_h, last_n=last_n, k=k)
        tag_a, *_ = regression_flag(s_a, last_n=last_n, k=k)
        out[kind] = {"home": tag_h, "away": tag_a}
    return out


def regression_icon_for_market(market: str, flags: Dict[str, Dict[str, str]]) -> str:
    m = str(market).lower()
    kind = None
    if "over 2.5" in m or "o2.5" in m:
        kind = "over25"
    elif "under 2.5" in m or "u2.5" in m:
        kind = "over25"  # usa o mesmo sinal (alto over => risco para unders)
    elif "btts" in m or "ambas" in m:
        kind = "btts"
    elif "casa marca" in m:
        kind = "scored"
    elif "fora marca" in m:
        kind = "scored"
    if kind is None:
        return ""
    tag_h = flags.get(kind, {}).get("home", "")
    tag_a = flags.get(kind, {}).get("away", "")
    if ("⚡" in tag_h) or ("⚡" in tag_a):
        return "⚡"
    if ("📉" in tag_h) or ("📉" in tag_a):
        return "📉"
    return ""


def overlay_form_df(serie: pd.DataFrame, home_team: str, away_team: str, kind: str, roll_n: int = 5) -> pd.DataFrame:
    """DataFrame para gráfico comparado (rolling no contexto Casa/Fora)."""
    def _df(team: str, venue: str, label: str) -> pd.DataFrame:
        d = serie[(serie["team"] == team) & (serie["venue"] == venue)].sort_values("date").copy()
        if d.empty:
            return pd.DataFrame(columns=["date", label])
        v = indicator_series(serie, team, venue, kind)
        d[label] = pd.to_numeric(v, errors="coerce").rolling(int(roll_n), min_periods=max(2, int(roll_n)//2)).mean()
        return d[["date", label]].dropna()

    dh = _df(home_team, "H", f"{home_team} (Casa)")
    da = _df(away_team, "A", f"{away_team} (Fora)")
    if dh.empty and da.empty:
        return pd.DataFrame()
    out = pd.merge(dh, da, on="date", how="outer").sort_values("date")
    return out


def form_series_context(serie: pd.DataFrame, team: str, venue: str, kind: str, roll_n: int = 5) -> pd.DataFrame:
    """Série (rolling) no contexto (Casa/Fora) para uma métrica. Devolve colunas: date, value."""
    d = serie[(serie["team"] == team) & (serie["venue"] == venue)].sort_values("date").copy()
    if d.empty:
        return pd.DataFrame(columns=["date", "value"])
    v = indicator_series(serie, team, venue, kind)
    roll_n = int(roll_n) if roll_n else 5
    v_roll = pd.to_numeric(v, errors="coerce").rolling(roll_n, min_periods=max(2, roll_n // 2)).mean()
    out = pd.DataFrame({"date": d["date"], "value": v_roll}).dropna()
    return out


def _pad_left_tail(values: np.ndarray, n: int) -> np.ndarray:
    """Devolve os últimos n valores (pad à esquerda com NaN se necessário)."""
    n = int(n)
    if n <= 0:
        return np.array([])
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if values.size >= n:
        return values[-n:]
    pad = np.full(n - values.size, np.nan, dtype=float)
    return np.concatenate([pad, values])


def plot_dual_series_matplotlib(
    x,
    series_map: Dict[str, np.ndarray],
    title: str,
    xlabel: str,
    ylabel: str,
    is_pct: bool = False,
):
    """Gráfico interactivo de linhas (Plotly) com anotação do último ponto."""
    plot_line_series_interactive(x=x, series_map=series_map, title=title, xlabel=xlabel, ylabel=ylabel, is_pct=is_pct)


def _style_posneg_series(s: pd.Series):
    """Styler.apply genérico (verde para >0, vermelho para <0)."""
    out = []
    for v in s:
        vv = pd.to_numeric(v, errors="coerce")
        if pd.isna(vv):
            out.append("")
        elif float(vv) > 0:
            out.append("background-color: rgba(0, 200, 0, 0.18); color: #0b3d0b; font-weight: 600;")
        elif float(vv) < 0:
            out.append("background-color: rgba(220, 0, 0, 0.16); color: #4a0b0b; font-weight: 600;")
        else:
            out.append("")
    return out


def recent_results_seq(serie: pd.DataFrame, team: str, venue: str, n: int = 5) -> List[str]:
    """Sequência dos últimos N resultados (W/D/L) no contexto (H/A)."""
    d = serie[(serie["team"] == team) & (serie["venue"] == venue)].sort_values("date").copy()
    if d.empty or "result" not in d.columns:
        return []
    return d["result"].fillna("?").astype(str).tail(n).tolist()


def render_result_badges(seq: List[str], label: str = "Últimos 5", size_px: int = 20):
    """Mostra W/D/L como círculos coloridos (contexto rápido)."""
    if not seq:
        st.caption(f"{label}: —")
        return
    cmap = {"W": "#2e7d32", "D": "#f9a825", "L": "#c62828"}
    html = f"<div style='display:flex;align-items:center;gap:6px'><span style='min-width:110px;color:#666'>{label}</span>"
    for ch in seq:
        c = cmap.get(str(ch).upper(), "#757575")
        html += (
            f"<span style='display:inline-block;width:{size_px}px;height:{size_px}px;"
            f"border-radius:999px;background:{c};color:white;text-align:center;"
            f"line-height:{size_px}px;font-weight:700;font-size:12px'>{str(ch).upper()}</span>"
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

def norm_cdf(z: float) -> float:
    """Normal CDF via erf (sem scipy)."""
    if pd.isna(z):
        return float("nan")
    return 0.5 * (1.0 + math.erf(float(z) / math.sqrt(2.0)))


def quadrant_scores(resumo_scope: pd.DataFrame, team_row: pd.Series) -> Dict[str, float]:
    """
    Radar por quadrantes (0..100) baseado em z-scores vs liga no mesmo contexto.
    Eixos:
      - Ataque (↑)
      - Defesa (↑; menor GA e menos remates/sot sofridos contam como melhor)
      - Cantos (↑; mais a favor e menos contra)
      - Disciplina (↑ = menos amarelos)
    """
    # z-scores por métrica (positivo=melhor)
    zdf = zscore_strengths(resumo_scope, team_row)

    def mean_z(cols: List[str]) -> float:
        d = zdf[zdf["col"].isin(cols)]["z"]
        d = pd.to_numeric(d, errors="coerce").dropna()
        if d.empty:
            return float("nan")
        return float(d.mean())

    z_attack = mean_z(["golos_marcados", "marca%", "SOT", "remates"])
    z_def = mean_z(["golos_sofridos", "CS%", "SOT_sofridos", "remates_sofridos"])
    z_corners = mean_z(["cantos", "cantos_sofridos"])
    z_disc = mean_z(["amarelos"])  # menor=melhor já foi invertido no zscore_strengths

    # converter z -> percentil -> 0..100
    out = {}
    for name, z in [("Ataque", z_attack), ("Defesa", z_def), ("Cantos", z_corners), ("Disciplina", z_disc)]:
        p = norm_cdf(z) if not pd.isna(z) else float("nan")
        out[name] = float(np.clip(p * 100.0, 0.0, 100.0)) if not pd.isna(p) else float("nan")
    return out


def plot_radar(scores: Dict[str, float], title: str = ""):
    """Radar simples com matplotlib (usa cores default)."""
    labels = list(scores.keys())
    values = [scores[k] if not pd.isna(scores[k]) else 0.0 for k in labels]
    # fechar o polígono
    values += values[:1]
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]

    fig = plt.figure(figsize=(4.5, 4.5))
    ax = plt.subplot(111, polar=True)
    ax.plot(angles, values, linewidth=2)
    ax.fill(angles, values, alpha=0.15)
    ax.set_thetagrids(np.degrees(angles[:-1]), labels)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"])
    if title:
        ax.set_title(title, pad=18)
    fig.tight_layout()
    return fig


def stability_index(serie: pd.DataFrame, team: str, venue: str, last_n: int = 6) -> float:
    """
    Índice 0..1 (1=estável). Baseado em variabilidade de golos (gf/ga) nos últimos N jogos.
    """
    d = serie[(serie["team"] == team) & (serie["venue"] == venue)].sort_values("date").copy()
    d = d.dropna(subset=["gf", "ga"])
    if len(d) < max(3, last_n):
        return float("nan")
    tail = d.tail(last_n)
    gf = pd.to_numeric(tail["gf"], errors="coerce")
    ga = pd.to_numeric(tail["ga"], errors="coerce")
    vol = float(np.nanmean([gf.std(ddof=0), ga.std(ddof=0)]))
    # mapear vol -> 0..1 (quanto maior vol, menos estável). 1.25 é um valor "alto" típico.
    return float(np.clip(1.0 - (vol / 1.25), 0.0, 1.0))


def sample_factor(games: float, full: float = 19.0) -> float:
    """0..1 com penalização suave (raiz)."""
    if pd.isna(games) or games <= 0:
        return 0.0
    return float(np.clip(math.sqrt(games) / math.sqrt(full), 0.0, 1.0))


def match_confidence(resumo: pd.DataFrame, serie: pd.DataFrame, home_team: str, away_team: str, recent_n: int = 6) -> Dict[str, float]:
    """
    Score de confiança 0..100:
    - amostra (Casa do mandante e Fora do visitante)
    - estabilidade recente (variância gf/ga)
    """
    home_row = get_team_scope_row(resumo, home_team, "Casa")
    away_row = get_team_scope_row(resumo, away_team, "Fora")
    if home_row is None or away_row is None:
        return {"conf_score": float("nan"), "factor_amostra": float("nan"), "factor_estabilidade": float("nan"), "jogos_casa": float("nan"), "jogos_fora": float("nan"), "stab_casa": float("nan"), "stab_fora": float("nan")}

    g_home = float(pd.to_numeric(home_row.get("jogos", np.nan), errors="coerce"))
    g_away = float(pd.to_numeric(away_row.get("jogos", np.nan), errors="coerce"))

    f_sample = sample_factor(min(g_home, g_away), full=19.0)

    stab_home = stability_index(serie, home_team, "H", last_n=recent_n)
    stab_away = stability_index(serie, away_team, "A", last_n=recent_n)
    # se faltar, assume neutro 0.5
    stab_home = 0.5 if pd.isna(stab_home) else stab_home
    stab_away = 0.5 if pd.isna(stab_away) else stab_away
    f_stab = float(np.clip((stab_home + stab_away) / 2.0, 0.0, 1.0))

    # score final (peso maior em amostra)
    score = 100.0 * (0.65 * f_sample + 0.35 * f_stab)

    return {
        "conf_score": float(np.clip(score, 0.0, 100.0)),
        "factor_amostra": f_sample,
        "factor_estabilidade": f_stab,
        "jogos_casa": g_home,
        "jogos_fora": g_away,
        "stab_casa": stab_home,
        "stab_fora": stab_away,
    }


def ev_from_odds(p: float, odds: float) -> Dict[str, float]:
    """
    EV por 1 unidade: p*odds - 1
    fair_odds = 1/p
    Kelly (fração) = (p*odds - 1)/(odds - 1) (se odds>1)
    """
    if pd.isna(p) or pd.isna(odds) or odds <= 1.0 or p <= 0 or p >= 1:
        return {"EV": float("nan"), "fair_odds": float("nan"), "kelly": float("nan")}
    ev = float(p * odds - 1.0)
    fair = float(1.0 / p)
    kelly = float((p * odds - 1.0) / (odds - 1.0))
    return {"EV": ev, "fair_odds": fair, "kelly": kelly}



def recent_form_rates(serie: pd.DataFrame, team: str, venue: str, last_n: int = 5) -> Dict[str, float]:
    """
    Médias recentes para a equipa, filtrando por venue ("H" ou "A").
    """
    d = serie[(serie["team"] == team) & (serie["venue"] == venue)].sort_values("date").copy()
    if d.empty:
        return {"gf": float("nan"), "ga": float("nan")}
    gf = _safe_per_game_series(d.get("gf", np.nan))
    ga = _safe_per_game_series(d.get("ga", np.nan))
    tail = pd.DataFrame({"gf": gf, "ga": ga}).dropna().tail(last_n)
    if tail.empty:
        return {"gf": float("nan"), "ga": float("nan")}
    return {
        "gf": float(pd.to_numeric(tail["gf"], errors="coerce").mean()),
        "ga": float(pd.to_numeric(tail["ga"], errors="coerce").mean()),
    }


@st.cache_data(show_spinner=False)
def expected_goals(resumo: pd.DataFrame, serie: pd.DataFrame, home_team: str, away_team: str,
                   weight_recent: float = 0.35, recent_n: int = 5,
                   alpha_ppg: float = 0.6, strength_k: float = 0.22) -> Tuple[float, float, Dict[str, float]]:
    """
    Combina 'season rates' (Resumo Casa/Fora) com forma recente (SerieTemporal) para estimar EG.
    weight_recent: 0..1
    """
    ref = league_reference(resumo)

    home_row = get_team_scope_row(resumo, home_team, "Casa")
    away_row = get_team_scope_row(resumo, away_team, "Fora")
    if home_row is None or away_row is None:
        return float("nan"), float("nan"), {}

    # season
    home_gf = float(pd.to_numeric(home_row.get("golos_marcados", np.nan), errors="coerce"))
    home_ga = float(pd.to_numeric(home_row.get("golos_sofridos", np.nan), errors="coerce"))
    away_gf = float(pd.to_numeric(away_row.get("golos_marcados", np.nan), errors="coerce"))
    away_ga = float(pd.to_numeric(away_row.get("golos_sofridos", np.nan), errors="coerce"))

    # recent (venue specific)
    rh = recent_form_rates(serie, home_team, "H", last_n=recent_n)
    ra = recent_form_rates(serie, away_team, "A", last_n=recent_n)

    def mix(season_val: float, recent_val: float) -> float:
        if (not np.isnan(season_val)) and (not np.isnan(recent_val)):
            return (1 - weight_recent) * season_val + weight_recent * recent_val
        if not np.isnan(season_val):
            return season_val
        if not np.isnan(recent_val):
            return recent_val
        return float("nan")

    home_gf_mix = mix(home_gf, float(rh.get("gf", np.nan)))
    home_ga_mix = mix(home_ga, float(rh.get("ga", np.nan)))
    away_gf_mix = mix(away_gf, float(ra.get("gf", np.nan)))
    away_ga_mix = mix(away_ga, float(ra.get("ga", np.nan)))

    # league baselines
    league_home_gf = ref.get("Casa:golos_marcados", np.nan)
    league_home_ga = ref.get("Casa:golos_sofridos", np.nan)
    league_away_gf = ref.get("Fora:golos_marcados", np.nan)
    league_away_ga = ref.get("Fora:golos_sofridos", np.nan)

    # strengths (multipliers)
    home_att = home_gf_mix / league_home_gf if league_home_gf and not np.isnan(league_home_gf) else np.nan
    home_def_weak = home_ga_mix / league_home_ga if league_home_ga and not np.isnan(league_home_ga) else np.nan
    away_att = away_gf_mix / league_away_gf if league_away_gf and not np.isnan(league_away_gf) else np.nan
    away_def_weak = away_ga_mix / league_away_ga if league_away_ga and not np.isnan(league_away_ga) else np.nan

    # expected goals (baseline * strength * opponent weakness)
    eg_home = (league_home_gf * home_att * away_def_weak) if all([not np.isnan(x) for x in [league_home_gf, home_att, away_def_weak]]) else np.nan
    eg_away = (league_away_gf * away_att * home_def_weak) if all([not np.isnan(x) for x in [league_away_gf, away_att, home_def_weak]]) else np.nan
    
    # Ajuste de força (PPG + diff_golos) para melhorar 1X2 em favoritos fortes
    # Mantém aproximadamente o total de golos, mas ajusta a razão (quem tem mais probabilidade de ganhar).
    strength_map = team_strength_scores(resumo, alpha_ppg=alpha_ppg)
    s_home = float(strength_map.get(home_team, 0.0))
    s_away = float(strength_map.get(away_team, 0.0))
    diff_strength = s_away - s_home  # positivo => visitante mais forte
    
    # aplica factor simétrico (ratio shift)
    f_home = math.exp(-strength_k * diff_strength / 2.0)
    f_away = math.exp(+strength_k * diff_strength / 2.0)
    
    if not np.isnan(eg_home):
        eg_home = float(eg_home * f_home)
    if not np.isnan(eg_away):
        eg_away = float(eg_away * f_away)
    
    debug = {
        "home_gf_season": home_gf,
        "home_ga_season": home_ga,
        "away_gf_season": away_gf,
        "away_ga_season": away_ga,
        "home_gf_recent": rh["gf"],
        "home_ga_recent": rh["ga"],
        "away_gf_recent": ra["gf"],
        "away_ga_recent": ra["ga"],
        "weight_recent": weight_recent,
        "alpha_ppg": alpha_ppg,
        "strength_k": strength_k,
        "strength_home": s_home,
        "strength_away": s_away,
        "diff_strength": diff_strength,
        "factor_home": f_home,
        "factor_away": f_away,
        "home_gf_mix": home_gf_mix,
        "home_ga_mix": home_ga_mix,
        "away_gf_mix": away_gf_mix,
        "away_ga_mix": away_ga_mix,
        "home_att_mult": home_att,
        "away_def_weak_mult": away_def_weak,
        "away_att_mult": away_att,
        "home_def_weak_mult": home_def_weak,
        "league_home_gf": league_home_gf,
        "league_home_ga": league_home_ga,
        "league_away_gf": league_away_gf,
        "league_away_ga": league_away_ga,
    }
    return float(eg_home), float(eg_away), debug


@st.cache_data(show_spinner=False)
def shortlist_markets(mercados: pd.DataFrame, home_team: str, away_team: str, min_games: int = 8) -> pd.DataFrame:
    """
    Faz shortlist combinando edges Casa do mandante e Fora do visitante.
    Inclui, se existirem no Excel, odds médias e alerta de tendência inversa.
    """
    mh = mercados[(mercados["team"] == home_team) & (mercados["scope"] == "Casa") & (mercados["jogos"] >= min_games)].copy()
    ma = mercados[(mercados["team"] == away_team) & (mercados["scope"] == "Fora") & (mercados["jogos"] >= min_games)].copy()
    if mh.empty or ma.empty:
        return pd.DataFrame()

    j = mh.merge(ma, on="market", suffixes=("_casa", "_fora"))
    j["edge_media"] = j[["edge_vs_liga_casa", "edge_vs_liga_fora"]].mean(axis=1)
    # penalização por amostra pequena (suave): usa sqrt dos jogos
    j["peso"] = np.sqrt(j[["jogos_casa", "jogos_fora"]].min(axis=1).clip(lower=1))
    j["score"] = j["edge_media"] * j["peso"]

    # alerta tendência inversa (qualquer lado)
    if ("alerta_tendencia_inversa_casa" in j.columns) or ("alerta_tendencia_inversa_fora" in j.columns):
        a1 = j.get("alerta_tendencia_inversa_casa", False)
        a2 = j.get("alerta_tendencia_inversa_fora", False)
        j["alerta"] = (a1.fillna(False).astype(bool) | a2.fillna(False).astype(bool)).map(lambda x: "⚠️" if x else "")
    else:
        j["alerta"] = ""

    # value estimado por lado (se houver odds médias)
    if "odds_avg_casa" in j.columns:
        j["value_est_casa"] = j.apply(lambda r: value_estimado(r.get("hit_rate_casa", np.nan), r.get("odds_avg_casa", np.nan)), axis=1)
    if "odds_avg_fora" in j.columns:
        j["value_est_fora"] = j.apply(lambda r: value_estimado(r.get("hit_rate_fora", np.nan), r.get("odds_avg_fora", np.nan)), axis=1)

    cols = [
        "alerta",
        "market",
        "edge_vs_liga_casa", "edge_vs_liga_fora", "edge_media",
        "hit_rate_casa", "hit_rate_fora",
        "roi_unid_por_aposta_casa", "roi_unid_por_aposta_fora",
        "jogos_casa", "jogos_fora",
    ]

    # opcionais
    for c in ["odds_avg_casa", "odds_avg_fora", "value_est_casa", "value_est_fora"]:
        if c in j.columns:
            cols.append(c)

    cols.append("score")
    return j[cols].sort_values("score", ascending=False, na_position="last")

MARKET_GROUPS = {
    "Golos": [
        "Over 1.5", "Over 2.5", "Under 2.5", "Under 3.5",
        "Over 2.5 golos", "Under 2.5 golos", "Over 1.5 golos", "Over 3.5 golos",
        "Ambas marcam (BTTS)", "BTTS", "BTTS Sim",
        "Casa marca (>=1)", "Fora marca (>=1)",
    ],
    "Clean sheets": [
        "Clean sheet", "CS", "CS%",
    ],
    "Resultados (1X2)": [
        "Vitória (1X2)", "1", "2", "X",
    ],
    "Handicap": [
        "Handicap Asiático (AH)", "AH",
    ],
    "Cantos": [
        "Cantos", "Over cantos", "Under cantos",
    ],
    "Cartões/Disciplina": [
        "Cartões", "Amarelos", "Vermelhos",
    ],
}


def zscore_strengths(resumo_scope: pd.DataFrame, team_row: pd.Series) -> pd.DataFrame:
    """
    Z-score por métrica dentro do scope (Total/Casa/Fora).
    Inverte sinal quando "menor é melhor", para que positivo = melhor.
    """
    rows = []
    for m in METRICS:
        if m.col not in resumo_scope.columns:
            continue
        series = pd.to_numeric(resumo_scope[m.col], errors="coerce")
        mu = series.mean()
        sd = series.std(ddof=0)
        val = pd.to_numeric(team_row.get(m.col, np.nan), errors="coerce")
        if pd.isna(val) or sd == 0 or pd.isna(sd):
            z = np.nan
        else:
            z = (val - mu) / sd
        if not m.higher_is_better and not pd.isna(z):
            z = -z
        rows.append(
            {
                "grupo": m.group,
                "métrica": m.label,
                "col": m.col,
                "valor": val,
                "z": z,
                "melhor_quando": "↑" if m.higher_is_better else "↓",
            }
        )
    df = pd.DataFrame(rows).sort_values("z", ascending=False, na_position="last")
    return df


def pick_strengths_weaknesses(zdf: pd.DataFrame, n: int = 5) -> Tuple[pd.DataFrame, pd.DataFrame]:
    good = zdf.dropna(subset=["z"]).sort_values("z", ascending=False).head(n)
    bad = zdf.dropna(subset=["z"]).sort_values("z", ascending=True).head(n)
    return good, bad


def safe_team_list(resumo: pd.DataFrame) -> List[str]:
    return sorted(resumo["team"].dropna().unique().tolist())


def render_kpis(team_row: pd.Series):
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Pontos/jogo", fmt_num(team_row.get("ppg", np.nan)))
    c2.metric("Golos marcados/jogo", fmt_num(team_row.get("golos_marcados", np.nan)))
    c3.metric("Golos sofridos/jogo", fmt_num(team_row.get("golos_sofridos", np.nan)))

    if ("xg_impl" in team_row.index) and pd.notna(team_row.get("xg_impl", np.nan)):
        c4.metric("xG implícito/jogo", fmt_num(team_row.get("xg_impl", np.nan)))
    else:
        c4.metric("% a marcar", fmt_pct(team_row.get("marca%", np.nan)))

    c5.metric("% Clean sheets", fmt_pct(team_row.get("CS%", np.nan)))



def format_resumo_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if c in PERCENT_COLS:
            out[c] = out[c].apply(fmt_pct)
        elif c not in {"team", "scope"}:
            out[c] = pd.to_numeric(out[c], errors="coerce").apply(fmt_num)
    return out


def format_mercados_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # hit_rate (se existir)
    if "hit_rate" in out.columns:
        out["hit_rate"] = out["hit_rate"].apply(fmt_pct)

    # hit_rate com IC (já vem como string)
    if "hit_rate_ic90" in out.columns:
        out["hit_rate_ic90"] = out["hit_rate_ic90"].astype(str)

    if "edge_vs_liga" in out.columns:
        out["edge_vs_liga"] = out["edge_vs_liga"].apply(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f} pp")

    if "roi_unid_por_aposta" in out.columns:
        out["roi_unid_por_aposta"] = out["roi_unid_por_aposta"].apply(fmt_roi)

    if "odds_avg" in out.columns:
        out["odds_avg"] = pd.to_numeric(out["odds_avg"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")

    if "fair_odds_hit" in out.columns:
        out["fair_odds_hit"] = pd.to_numeric(out["fair_odds_hit"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")

    if "value_est" in out.columns:
        out["value_est"] = pd.to_numeric(out["value_est"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f}%")

    if "alerta" in out.columns:
        out["alerta"] = out["alerta"].astype(str)

    # colunas extra (se existirem) usadas no Pré-jogo
    for c in ["odds", "fair_odds", "p_hist", "value"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").apply(lambda x: "—" if pd.isna(x) else (f"{x:.2f}" if c in {"odds","fair_odds"} else f"{x*100:+.1f}%"))

    return out


# ----------------------------
# Trading Lay helpers (UI)
# ----------------------------

def _style_lay_hit_rate_series(s: pd.Series):
    """Hit rate baixo = bom para lay. Verde para raro, vermelho para frequente."""
    out = []
    for v in s:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            out.append("")
            continue
        vv = None
        if isinstance(v, str):
            vv_str = v.strip().replace("%", "").replace(",", ".")
            try:
                vv = float(vv_str)
                if vv > 1.0:
                    vv = vv / 100.0
            except Exception:
                vv = None
        else:
            try:
                vv = float(v)
            except Exception:
                vv = None
        if vv is None or (isinstance(vv, float) and np.isnan(vv)):
            out.append("")
            continue
        if vv <= 0.25:
            out.append("background-color: rgba(0, 200, 0, 0.18); color: #0b3d0b; font-weight: 600;")
        elif vv <= 0.45:
            out.append("background-color: rgba(255, 193, 7, 0.18); color: #6b4f00; font-weight: 600;")
        else:
            out.append("background-color: rgba(220, 0, 0, 0.16); color: #4a0b0b; font-weight: 600;")
    return out


def _pill_html(label: str, value_txt: str = "", kind: str = "good") -> str:
    # kind: good/warn/bad/neutral
    palette = {
        "good": ("rgba(0,200,0,0.16)", "#0b3d0b"),
        "warn": ("rgba(255,193,7,0.18)", "#6b4f00"),
        "bad": ("rgba(220,0,0,0.14)", "#4a0b0b"),
        "neutral": ("rgba(120,120,120,0.12)", "#333333"),
    }
    bg, fg = palette.get(kind, palette["neutral"])
    val = f" <span style='opacity:0.85'>({value_txt})</span>" if value_txt else ""
    return (
        f"<span style='display:inline-block;padding:4px 10px;border-radius:999px;"
        f"background:{bg};color:{fg};font-weight:700;font-size:12px;margin:0 6px 6px 0;'>"
        f"{label}{val}</span>"
    )


def render_lay_pills(df: pd.DataFrame, max_pills: int = 6, title: str = "Leitura rápida"):
    """Mostra pills dos cenários mais improváveis."""
    if df is None or df.empty:
        st.caption(f"{title}: —")
        return
    d = df.sort_values(["lay_score", "hit_rate"], ascending=[False, True]).head(int(max_pills)).copy()
    pills = []
    for _, r in d.iterrows():
        scen = str(r.get("cenario_lay", "—"))
        hit = pd.to_numeric(r.get("hit_rate", np.nan), errors="coerce")
        hit_txt = "—" if pd.isna(hit) else f"{hit*100:.0f}%"
        kind = "good" if (pd.notna(hit) and float(hit) <= 0.25) else "warn" if (pd.notna(hit) and float(hit) <= 0.45) else "bad"
        mark = "✅ " if bool(r.get("flag_candidato", False)) else ""
        pills.append(_pill_html(f"{mark}{scen}", hit_txt, kind=kind))
    st.markdown("<div style='display:flex;flex-wrap:wrap;align-items:center'>" + "".join(pills) + "</div>", unsafe_allow_html=True)


def lay_candidates_for_team(lay_df: pd.DataFrame, team: str, scope: str, top_n: int = 10) -> pd.DataFrame:
    if lay_df is None or lay_df.empty:
        return pd.DataFrame()
    d = lay_df[(lay_df["team"] == team) & (lay_df["scope"] == scope)].copy()
    if d.empty:
        return d
    d = d.sort_values(["lay_score", "hit_rate"], ascending=[False, True]).head(int(top_n))
    return d


def lay_table_view(df: pd.DataFrame) -> Tuple[pd.DataFrame, 'pd.io.formats.style.Styler']:
    """Cria view formatada + Styler (hit_rate e flag)."""
    if df is None or df.empty:
        empty = pd.DataFrame(columns=["cenario_lay", "hit_rate", "IC", "edge_vs_liga", "lay_score", "flag"])
        return empty, empty.style

    d = df.copy()
    d["IC"] = d.apply(
        lambda r: "—" if (pd.isna(r.get("wilson_lo")) or pd.isna(r.get("wilson_hi")))
        else f"{float(r['wilson_lo'])*100:.0f}%–{float(r['wilson_hi'])*100:.0f}%",
        axis=1,
    )
    d["edge_vs_liga"] = pd.to_numeric(d.get("edge_vs_liga"), errors="coerce")
    d["lay_score"] = pd.to_numeric(d.get("lay_score"), errors="coerce")
    d["hit_rate"] = pd.to_numeric(d.get("hit_rate"), errors="coerce")
    d["flag"] = d.get("flag_candidato", False).apply(lambda x: "✅" if bool(x) else "")

    view = d[["cenario_lay", "hit_rate", "IC", "edge_vs_liga", "lay_score", "flag"]].copy()
    # formato
    view["hit_rate"] = view["hit_rate"].apply(lambda x: "—" if pd.isna(x) else f"{x*100:.1f}%")
    view["edge_vs_liga"] = view["edge_vs_liga"].apply(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f} pp")
    view["lay_score"] = view["lay_score"].apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")

    # para estilo precisamos de uma coluna numérica paralela
    style_base = d[["cenario_lay", "hit_rate", "IC", "edge_vs_liga", "lay_score", "flag"]].copy()
    styler = view.style

    # corrar hit_rate com base na coluna numérica original
    try:
        # construir um series com valores numéricos alinhados
        hit_num = style_base["hit_rate"]
        styler = styler.apply(_style_lay_hit_rate_series, subset=["hit_rate"], axis=0)
    except Exception:
        pass
    return view, styler


def lay_convergent_table(df_home: pd.DataFrame, df_away: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Cenários convergentes: aparecem nos top N de ambos."""
    if df_home is None or df_away is None or df_home.empty or df_away.empty:
        return pd.DataFrame()

    a = df_home.sort_values(["lay_score", "hit_rate"], ascending=[False, True]).head(int(top_n)).copy()
    b = df_away.sort_values(["lay_score", "hit_rate"], ascending=[False, True]).head(int(top_n)).copy()

    j = a.merge(b, on="cenario_lay", suffixes=("_casa", "_fora"))
    if j.empty:
        return j
    # score convergente (min dos dois: abordagem conservadora)
    j["score_min"] = j[["lay_score_casa", "lay_score_fora"]].min(axis=1)
    j = j.sort_values("score_min", ascending=False)

    out = pd.DataFrame({
        "cenario_lay": j["cenario_lay"],
        "hit_casa": j["hit_rate_casa"],
        "hit_fora": j["hit_rate_fora"],
        "IC_hi_casa": j["wilson_hi_casa"],
        "IC_hi_fora": j["wilson_hi_fora"],
        "lay_score_casa": j["lay_score_casa"],
        "lay_score_fora": j["lay_score_fora"],
        "score_min": j["score_min"],
    })

    # format
    out["hit_casa"] = out["hit_casa"].apply(lambda x: "—" if pd.isna(x) else f"{x*100:.1f}%")
    out["hit_fora"] = out["hit_fora"].apply(lambda x: "—" if pd.isna(x) else f"{x*100:.1f}%")
    out["IC_hi_casa"] = out["IC_hi_casa"].apply(lambda x: "—" if pd.isna(x) else f"{x*100:.0f}%")
    out["IC_hi_fora"] = out["IC_hi_fora"].apply(lambda x: "—" if pd.isna(x) else f"{x*100:.0f}%")
    for c in ["lay_score_casa", "lay_score_fora", "score_min"]:
        out[c] = out[c].apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
    return out

def download_button(df: pd.DataFrame, filename: str, label: str):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, data=csv, file_name=filename, mime="text/csv")


def matchup_insights(home: pd.Series, away: pd.Series) -> List[str]:
    """
    Heurísticas simples para "insights" baseados no Resumo:
    - Não são previsões; apenas ângulos a explorar.
    """
    insights = []

    # Probabilidade de a equipa da casa marcar
    if (home.get("marca%", np.nan) >= 0.80) and (away.get("CS%", np.nan) <= 0.25):
        insights.append("Ângulo: **Casa marca (>=1)** — equipa da casa marca com muita frequência e o adversário fora tem poucos clean sheets.")

    # Under/Over
    if (home.get("U2.5%", np.nan) >= 0.60) and (away.get("U2.5%", np.nan) >= 0.60):
        insights.append("Ângulo: **Under 2.5** — ambos têm perfil de jogos mais fechados (>=60% Under 2.5 no contexto seleccionado).")
    if (home.get("O2.5%", np.nan) >= 0.60) and (away.get("O2.5%", np.nan) >= 0.60):
        insights.append("Ângulo: **Over 2.5** — ambos tendem a jogos abertos (>=60% Over 2.5 no contexto seleccionado).")

    # BTTS
    if (home.get("BTTS%", np.nan) >= 0.60) and (away.get("BTTS%", np.nan) >= 0.60):
        insights.append("Ângulo: **BTTS (Ambas marcam)** — ambos têm % BTTS elevada no contexto seleccionado.")

    # Pressão / cantos
    if (home.get("cantos", np.nan) >= 5.5) and (away.get("cantos_sofridos", np.nan) >= 5.0):
        insights.append("Ângulo: **Cantos (Casa)** — equipa da casa ganha muitos cantos e o adversário concede muitos fora.")

    # Defesa frágil do visitante
    if (away.get("golos_sofridos", np.nan) >= 1.6) and (home.get("golos_marcados", np.nan) >= 1.5):
        insights.append("Ângulo: **Casa (golos / mercados pró-casa)** — ataque da casa forte vs defesa fora frágil (médias elevadas).")

    return insights



# ----------------------------
# Análise automática da forma (heurística)
# ----------------------------

FORM_METRICS_META = {
    "roll5_points": {"label": "Pontos (média móvel 5)", "higher_is_better": True, "kind": "points"},
    "roll5_gf": {"label": "Golos marcados (média móvel 5)", "higher_is_better": True, "kind": "goals_for"},
    "roll5_ga": {"label": "Golos sofridos (média móvel 5)", "higher_is_better": False, "kind": "goals_against"},
    "roll5_goal_diff": {"label": "Diferença de golos (média móvel 5)", "higher_is_better": True, "kind": "goal_diff"},
    "roll5_over_2_5": {"label": "Over 2.5 (taxa, média móvel 5)", "higher_is_better": True, "kind": "rate"},
    "roll5_under_2_5": {"label": "Under 2.5 (taxa, média móvel 5)", "higher_is_better": True, "kind": "rate"},
    "roll5_btts": {"label": "BTTS (taxa, média móvel 5)", "higher_is_better": True, "kind": "rate"},
    "roll5_team_scored": {"label": "Equipa marcou (taxa, média móvel 5)", "higher_is_better": True, "kind": "rate"},
    "roll5_clean_sheet": {"label": "Clean sheets (taxa, média móvel 5)", "higher_is_better": True, "kind": "rate"},
}

def _lin_slope(values: np.ndarray) -> float:
    """Inclinação por jogo (regressão linear simples)."""
    if values.size < 3:
        return float("nan")
    x = np.arange(values.size, dtype=float)
    # polyfit grau 1: y = a*x + b
    a = np.polyfit(x, values.astype(float), 1)[0]
    return float(a)

def _fmt_delta(v: float, kind: str) -> str:
    if pd.isna(v):
        return "—"
    # em taxas (0..1), mostrar em pp
    if kind == "rate":
        return f"{v*100:+.1f} pp"
    return f"{v:+.2f}"

def _fmt_val(v: float, kind: str) -> str:
    if pd.isna(v):
        return "—"
    if kind == "rate":
        return f"{v*100:.0f}%"
    return f"{v:.2f}"

def form_insights(dft_team: pd.DataFrame, metric: str, resumo_liga: Optional[pd.DataFrame] = None) -> List[str]:
    """
    Gera notas automáticas (estilo analista) sobre a série do gráfico.
    - Baseado em tendência (inclinação), nível vs média da época, consistência e "pontos de viragem".
    - Acrescenta leitura Casa vs Fora e dificuldade do calendário (proxy via PPG dos adversários), quando possível.
    - Heurístico: não é previsão.
    """
    meta = FORM_METRICS_META.get(metric, {"label": metric, "higher_is_better": True, "kind": "other"})
    kind = meta["kind"]
    hib = bool(meta.get("higher_is_better", True))

    # Série do gráfico (rolling)
    dfm = dft_team[["date", "opponent", "venue", metric]].copy() if all(c in dft_team.columns for c in ["date", "opponent", "venue"]) else dft_team[[metric]].copy()
    dfm[metric] = pd.to_numeric(dfm[metric], errors="coerce")
    dfm = dfm.dropna(subset=[metric]).sort_values("date") if "date" in dfm.columns else dfm.dropna(subset=[metric])

    if dfm.shape[0] < 4:
        return ["Sem jogos suficientes para tirar conclusões robustas com esta métrica."]

    s = dfm[metric].astype(float)

    # Janelas para leitura
    k_trend = int(min(10, s.size))
    k_short = int(min(5, s.size))

    tail_trend = s.tail(k_trend).to_numpy(dtype=float)
    tail_short = s.tail(k_short).to_numpy(dtype=float)

    latest = float(tail_trend[-1])

    # Tendência (slope) + thresholds por tipo
    slope = _lin_slope(tail_trend)
    thr = 0.02 if kind == "rate" else 0.06  # variação por jogo (heurística)
    # se menor é melhor, inverte sinal para a leitura textual
    slope_read = (-slope) if (not hib and not pd.isna(slope)) else slope

    def _trend_label(sl: float) -> str:
        if pd.isna(sl):
            return "indefinida"
        if sl > thr:
            return "melhoria"
        if sl < -thr:
            return "quebra"
        return "estável"

    trend_txt = _trend_label(slope_read)

    # Nível vs época
    season_mean = float(s.mean())
    season_std = float(s.std(ddof=0)) if s.size >= 6 else float("nan")
    z = (latest - season_mean) / season_std if (season_std and not pd.isna(season_std) and season_std > 1e-9) else float("nan")
    z_read = (-z) if (not hib and not pd.isna(z)) else z  # positivo = melhor

    # Curto prazo vs médio prazo
    mean_short = float(np.nanmean(tail_short))
    mean_prev_short = float(np.nanmean(s.tail(k_short * 2).head(k_short))) if s.size >= k_short * 2 else float("nan")
    delta_short = mean_short - mean_prev_short if not pd.isna(mean_prev_short) else float("nan")
    if not hib and not pd.isna(delta_short):
        delta_short = -delta_short  # leitura: positivo = melhor

    # Consistência (volatilidade)
    vol_short = float(np.nanstd(tail_trend))
    vol_season = float(np.nanstd(s.to_numpy(dtype=float)))
    vol_ratio = (vol_short / vol_season) if (vol_season and not pd.isna(vol_season) and vol_season > 1e-9) else float("nan")

    # Extremos recentes
    recent_max = float(np.nanmax(tail_trend))
    recent_min = float(np.nanmin(tail_trend))
    is_near_max = (abs(latest - recent_max) <= (0.03 if kind == "rate" else 0.08))
    is_near_min = (abs(latest - recent_min) <= (0.03 if kind == "rate" else 0.08))

    notes: List[str] = []

    # 1) Headline
    notes.append(f"**{meta['label']}**: {_fmt_val(latest, kind)} • tendência de **{trend_txt}** nos últimos {k_trend} jogos (média móvel).")

    # 2) Momento
    if not pd.isna(delta_short):
        notes.append(
            f"**Momento**: nos últimos {k_short} jogos a média móvel está "
            f"{'melhor' if delta_short > 0 else 'pior' if delta_short < 0 else 'sem mudança'} "
            f"vs os {k_short} anteriores ({_fmt_delta(delta_short, kind)})."
        )

    # 3) Nível vs época (z-score)
    if not pd.isna(z_read):
        if z_read >= 0.75:
            notes.append("**Nível**: acima do normal para esta equipa nesta época (bom patamar recente).")
        elif z_read <= -0.75:
            notes.append("**Nível**: abaixo do normal para esta equipa nesta época (fase menos conseguida).")
        else:
            notes.append("**Nível**: alinhado com a média da época (sem desvio grande).")

    # 4) Consistência
    if not pd.isna(vol_ratio):
        if vol_ratio >= 1.25:
            notes.append("**Consistência**: forma recente irregular (oscila mais do que o habitual).")
        elif vol_ratio <= 0.85:
            notes.append("**Consistência**: forma recente consistente/estável (pouca oscilação).")

    # 5) Extremos (alertas)
    if is_near_max:
        notes.append("**Alerta**: está perto do melhor registo recente nesta métrica.")
    if is_near_min:
        notes.append("**Alerta**: está perto do pior registo recente nesta métrica.")

    # 6) Pontos de viragem (detecção simples de mudança de inclinação)
    try:
        L = int(min(20, s.size))
        w = 5 if L >= 12 else 4
        tail = s.tail(L).to_numpy(dtype=float)
        # procurar o ponto em que a inclinação muda mais (antes vs depois)
        best = {"i": None, "change": 0.0, "sb": float("nan"), "sa": float("nan")}
        for i in range(w, L - w + 1):
            sb = _lin_slope(tail[i - w : i])
            sa = _lin_slope(tail[i : i + w])
            if pd.isna(sb) or pd.isna(sa):
                continue
            # leitura: positivo = melhor
            sb_r = (-sb) if (not hib) else sb
            sa_r = (-sa) if (not hib) else sa
            ch = abs(sa_r - sb_r)
            if ch > best["change"]:
                best = {"i": i, "change": ch, "sb": sb_r, "sa": sa_r}
        if best["i"] is not None and best["change"] >= (thr * 1.8):
            idx0 = dfm.shape[0] - L
            pivot_row = dfm.iloc[idx0 + int(best["i"])]
            pivot_date = pivot_row["date"].date().isoformat() if "date" in pivot_row else ""
            pivot_opp = pivot_row.get("opponent", "—")
            pivot_venue = pivot_row.get("venue", "")
            before_lbl = _trend_label(best["sb"])
            after_lbl = _trend_label(best["sa"])
            if before_lbl != after_lbl:
                where = ("em casa" if pivot_venue == "H" else "fora" if pivot_venue == "A" else "").strip()
                where = f" ({where})" if where else ""
                notes.append(
                    f"**Ponto de viragem (provável)**: por volta de **{pivot_date}**{where}, a tendência passou de **{before_lbl}** para **{after_lbl}** (jogo vs {pivot_opp})."
                )
    except Exception:
        pass

    # 7) Sequência recente (W/D/L + pontos) + leitura táctica leve
    if all(c in dft_team.columns for c in ["result", "points", "gf", "ga", "date"]):
        last6 = dft_team.sort_values("date").tail(6).copy()
        if not last6.empty:
            seq = "".join(last6["result"].fillna("?").astype(str).tolist())
            pts = int(pd.to_numeric(last6["points"], errors="coerce").fillna(0).sum())
            gf6 = float(pd.to_numeric(last6["gf"], errors="coerce").fillna(0).sum())
            ga6 = float(pd.to_numeric(last6["ga"], errors="coerce").fillna(0).sum())
            gd6 = gf6 - ga6
            notes.append(f"**Série (6 jogos)**: `{seq}` • **{pts} pts** • golos **{gf6:.0f}-{ga6:.0f}** (diff {gd6:+.0f}).")

            # “sustentabilidade” simples: pontos vs diff
            if pts >= 12 and gd6 <= 1:
                notes.append("**Leitura**: muitos pontos com margens curtas — pode ser eficácia/gestão de vantagens; atenção a regressão se o volume de jogo não acompanhar.")
            elif pts <= 5 and gd6 >= 0:
                notes.append("**Leitura**: resultados aquém do que o saldo de golos sugere — pode haver detalhe (bola parada/erros) a penalizar mais do que o jogo produzido.")
            elif pts <= 5 and gd6 <= -4:
                notes.append("**Leitura**: fase de controlo defensivo frágil (saldo negativo pesado) — normalmente melhora quando estabiliza a última linha e reduz erros.")
            elif pts >= 12 and gd6 >= 6:
                notes.append("**Leitura**: fase forte e dominadora (saldo de golos alto) — costuma traduzir confiança e criação de ocasiões.")

    # 8) Casa vs Fora (separação por contexto nos jogos recentes)
    if all(c in dft_team.columns for c in ["venue", "points", "gf", "ga", "over_2_5", "btts", "date"]):
        df_sorted = dft_team.sort_values("date").copy()
        home = df_sorted[df_sorted["venue"] == "H"].tail(6)
        away = df_sorted[df_sorted["venue"] == "A"].tail(6)

        def _ctx_line(df_ctx: pd.DataFrame, label: str) -> Optional[str]:
            if df_ctx.empty:
                return None
            ppg = pd.to_numeric(df_ctx["points"], errors="coerce").mean()
            gf = pd.to_numeric(df_ctx["gf"], errors="coerce").mean()
            ga = pd.to_numeric(df_ctx["ga"], errors="coerce").mean()
            # taxas
            o25 = pd.to_numeric(df_ctx.get("over_2_5", np.nan), errors="coerce").mean() if "over_2_5" in df_ctx.columns else np.nan
            btts = pd.to_numeric(df_ctx.get("btts", np.nan), errors="coerce").mean() if "btts" in df_ctx.columns else np.nan
            bits = []
            if not pd.isna(ppg):
                bits.append(f"{ppg:.2f} pts/j")
            if not pd.isna(gf) and not pd.isna(ga):
                bits.append(f"GF {gf:.2f} / GA {ga:.2f}")
            if not pd.isna(o25):
                bits.append(f"O2.5 {_fmt_val(o25, 'rate')}")
            if not pd.isna(btts):
                bits.append(f"BTTS {_fmt_val(btts, 'rate')}")
            return f"**{label}** (últimos {len(df_ctx)}): " + " • ".join(bits)

        h_line = _ctx_line(home, "Em casa")
        a_line = _ctx_line(away, "Fora")
        if h_line or a_line:
            notes.append("**Casa vs Fora** (últimos 6 em cada contexto):")
            if h_line:
                notes.append(h_line)
            if a_line:
                notes.append(a_line)

            # frase interpretativa simples
            if not home.empty and not away.empty:
                h_ppg = pd.to_numeric(home["points"], errors="coerce").mean()
                a_ppg = pd.to_numeric(away["points"], errors="coerce").mean()
                if (not pd.isna(h_ppg)) and (not pd.isna(a_ppg)) and abs(h_ppg - a_ppg) >= 0.45:
                    if h_ppg > a_ppg:
                        notes.append("**Leitura**: há sinal de dependência do factor casa no período recente (pontua bem mais em casa do que fora).")
                    else:
                        notes.append("**Leitura**: rendimento fora surpreendentemente melhor do que em casa no período recente (vale rever matchups e estilos).")

    # 9) Calendário (proxy de dificuldade via PPG total dos adversários na liga)
    if resumo_liga is not None and "team" in resumo_liga.columns and "ppg" in resumo_liga.columns:
        try:
            base = resumo_liga.copy()
            if "scope" in base.columns:
                base = base[base["scope"] == "Total"].copy()
            ppg_map = pd.to_numeric(base.set_index("team")["ppg"], errors="coerce").to_dict()
            league_ppg = np.array([v for v in ppg_map.values() if pd.notna(v)], dtype=float)

            if "date" in dft_team.columns and "opponent" in dft_team.columns:
                lastN = dft_team.sort_values("date").tail(8).copy()
                opp_ppg = lastN["opponent"].map(ppg_map)
                avg_opp = float(pd.to_numeric(opp_ppg, errors="coerce").mean())
                if not pd.isna(avg_opp) and league_ppg.size >= 6:
                    pct = float((league_ppg < avg_opp).mean())  # 0..1
                    if pct >= 0.67:
                        lvl = "difícil (acima da média)"
                    elif pct <= 0.33:
                        lvl = "acessível (abaixo da média)"
                    else:
                        lvl = "misto/normal"
                    # top 2 adversários mais fortes recentes
                    tmp = lastN.assign(_opp_ppg=pd.to_numeric(opp_ppg, errors="coerce")).dropna(subset=["_opp_ppg"])
                    toughest = tmp.sort_values("_opp_ppg", ascending=False).head(2)
                    tough_txt = ""
                    if not toughest.empty:
                        parts = [f"{r['opponent']} ({r['_opp_ppg']:.2f} p/j)" for _, r in toughest.iterrows()]
                        tough_txt = " • mais fortes: " + ", ".join(parts)
                    notes.append(f"**Calendário recente (8 jogos)**: adversários com **{avg_opp:.2f} p/j** em média → {lvl}.{tough_txt}")
        except Exception:
            pass

    # 10) Leitura “táctica” (ajuda contextual) cruzando pontos/gf/ga (rolling, quando disponível)
    def _last(metric_name: str) -> float:
        if metric_name not in dft_team.columns:
            return float("nan")
        ss = pd.to_numeric(dft_team[metric_name], errors="coerce").dropna()
        return float(ss.iloc[-1]) if not ss.empty else float("nan")

    p = _last("roll5_points")
    gf = _last("roll5_gf")
    ga = _last("roll5_ga")

    if kind in {"points", "goals_for", "goals_against", "goal_diff"} and not (pd.isna(p) or pd.isna(gf) or pd.isna(ga)):
        def_trend = "sólida" if ga <= 1.0 else "permeável" if ga >= 1.6 else "normal"
        att_trend = "a carburar" if gf >= 1.6 else "curto" if gf <= 1.0 else "normal"

        if p >= 1.8 and ga <= 1.1:
            notes.append(f"**Leitura (perfil)**: equipa a pontuar bem e com defesa {def_trend}; tende a controlar jogos e a sofrer pouco.")
        elif p >= 1.8 and gf >= 1.6:
            notes.append(f"**Leitura (perfil)**: pontos altos com ataque {att_trend}; pode ser fase de criação/conversão acima da média.")
        elif p <= 1.0 and ga >= 1.6:
            notes.append(f"**Leitura (perfil)**: fase difícil, muito exposta atrás (GA recente alto) — erros/rupturas defensivas costumam pesar nos resultados.")
        elif p <= 1.0 and gf <= 1.0:
            notes.append(f"**Leitura (perfil)**: dificuldades ofensivas (GF recente baixo) — mesmo que a defesa não desmorone, falta produção para ganhar.")
        else:
            notes.append("**Leitura (perfil)**: momento relativamente equilibrado; para confirmar, cruza com calendário, ausências e estilo do adversário.")

    return notes



# ----------------------------
# UI
# ----------------------------
st.title("Dashboard Football teams - Data ")
st.caption("Carrega o relatório gerado pelo teu script e explora perfis, mercados e forma ao longo da época.")

with st.sidebar:
    st.header("Ficheiro")
    up = st.file_uploader("Upload do relatorio_equipas.xlsx", type=["xlsx"])
    st.caption("Se não fizeres upload, o app tenta ler `relatorio_equipas.xlsx` na pasta onde corres o Streamlit.")
    st.divider()
    st.header("Filtros globais")
    min_games = st.slider("Mínimo de jogos (para tabelas de mercados)", min_value=1, max_value=30, value=8, step=1)
    rolling_hint = st.info("A série temporal já traz o rolling do script (ex.: roll5_*).", icon="ℹ️")

try:
    dfs = load_report(up)
except Exception as e:
    st.error(str(e))
    st.stop()

resumo = dfs["Resumo"].copy()
mercados = dfs["Mercados"].copy()
serie = dfs["SerieTemporal"].copy()

# Trading Lay (opcional)
lay_cand_all = None
lay_top_all = None
if "Lay_Candidatos" in dfs:
    lay_cand_all = dfs["Lay_Candidatos"].copy()
elif "TradingScenarios" in dfs:
    lay_cand_all = dfs["TradingScenarios"].copy()

if "Lay_Top" in dfs:
    lay_top_all = dfs["Lay_Top"].copy()

resumo_all = resumo.copy()
mercados_all = mercados.copy()
serie_all = serie.copy()
lay_cand_all = lay_cand_all.copy() if lay_cand_all is not None else None
lay_top_all = lay_top_all.copy() if lay_top_all is not None else None

# Selecção de liga
all_leagues = sorted(resumo_all["league"].dropna().unique().tolist())
if not all_leagues:
    all_leagues = ["ALL"]

def league_label(code: str) -> str:
    name = LEAGUE_NAMES.get(code, "")
    return f"{code} — {name}" if name else code

with st.sidebar:
    st.header("Liga")
    # por defeito escolhe a 1ª liga encontrada
    league_sel = st.selectbox("Liga (Div)", options=all_leagues, format_func=league_label, index=0, key="league_sel")
    st.caption("O dashboard filtra tudo pela liga seleccionada (equipas, mercados, série temporal).")

# filtrar
resumo = resumo[resumo["league"] == league_sel].copy()
mercados = mercados[mercados["league"] == league_sel].copy()
serie = serie[serie["league"] == league_sel].copy()

lay_cand = lay_cand_all[lay_cand_all["league"] == league_sel].copy() if lay_cand_all is not None and ("league" in lay_cand_all.columns) else pd.DataFrame()
lay_top = lay_top_all[lay_top_all["league"] == league_sel].copy() if lay_top_all is not None and ("league" in lay_top_all.columns) else pd.DataFrame()


st.caption(f"Liga seleccionada: **{league_label(league_sel)}**")


teams = safe_team_list(resumo)
scopes = ["Total", "Casa", "Fora"]

# Tabs
tab_liga, tab_equipa, tab_merc, tab_forma, tab_prejogo, tab_lay, tab_scanner, tab_confronto = st.tabs(
    ["Liga", "Perfil da equipa", "Mercados", "Forma (série temporal)", "Pré-jogo", "🎯 Trading Lay", "Scanner (Multi-liga)", "Confronto"]
)

# ----------------------------
# Tab: Liga
# ----------------------------
with tab_liga:
    st.subheader(f"Visão geral da liga • {league_label(league_sel)}")
    colA, colB = st.columns([2, 1])

    with colB:
        scope_sel = st.selectbox("Contexto", scopes, index=0, key="liga_scope")
        show_raw = st.toggle("Mostrar tabela completa", value=False)

    df_scope = resumo[resumo["scope"] == scope_sel].copy()

    # Rankings rápidos
    rank_cols = [
        ("ppg", "Pontos/jogo"),
        ("golos_marcados", "Golos marcados/jogo"),
        ("golos_sofridos", "Golos sofridos/jogo (↓)"),
        ("CS%", "% Clean sheets"),
        ("O2.5%", "% Over 2.5"),
        ("BTTS%", "% BTTS"),
    ]

    with colA:
        c1, c2, c3 = st.columns(3)
        c1.dataframe(
            format_resumo_table(df_scope.sort_values("ppg", ascending=False)[["team", "scope", "jogos", "ppg", "vit%", "emp%", "der%"]]),
            use_container_width=True,
            hide_index=True,
        )
        c2.dataframe(
            format_resumo_table(df_scope.sort_values("golos_marcados", ascending=False)[["team", "scope", "jogos", "golos_marcados", "marca%", "SOT", "cantos"]]),
            use_container_width=True,
            hide_index=True,
        )
        c3.dataframe(
            format_resumo_table(df_scope.sort_values("golos_sofridos", ascending=True)[["team", "scope", "jogos", "golos_sofridos", "CS%", "SOT_sofridos", "remates_sofridos"]]),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.markdown("#### Médias da liga (por contexto)")
    st.dataframe(format_resumo_table(compute_league_means(resumo)), use_container_width=True, hide_index=True)

    if show_raw:
        st.markdown("#### Tabela completa (Resumo)")
        st.dataframe(format_resumo_table(df_scope), use_container_width=True, hide_index=True)
        download_button(df_scope, f"resumo_{scope_sel.lower()}.csv", f"Descarregar Resumo ({scope_sel}) em CSV")

# ----------------------------
# Tab: Perfil da equipa
# ----------------------------
with tab_equipa:
    st.subheader("Perfil da equipa")
    col1, col2 = st.columns([1, 1])

    with col1:
        team_sel = st.selectbox("Equipa", teams, index=0, key="team_sel")
    with col2:
        scope_sel = st.selectbox("Contexto (Total/Casa/Fora)", scopes, index=0, key="team_scope")

    df_scope = resumo[resumo["scope"] == scope_sel].copy()
    team_row = get_team_scope_row(df_scope, team_sel, scope_sel)
    if team_row is None:
        st.warning("Sem dados da equipa para o contexto seleccionado.")
        st.stop()

    render_kpis(team_row)

    zdf = zscore_strengths(df_scope, team_row)
    strengths, weaknesses = pick_strengths_weaknesses(zdf, n=6)

    st.markdown("### Pontos fortes / fracos (vs média da liga no mesmo contexto)")
    s1, s2 = st.columns(2)
    with s1:
        st.markdown("**Pontos fortes (z-score mais alto)**")
        show = strengths[["grupo", "métrica", "col", "valor", "z"]].copy()
        show["valor"] = show.apply(lambda r: fmt_pct(r["valor"]) if r["col"] in PERCENT_COLS else fmt_num(r["valor"]), axis=1)
        show["z"] = show["z"].map(lambda x: f"{x:+.2f}")
        st.dataframe(show.drop(columns=["col"]), hide_index=True, use_container_width=True)
    with s2:
        st.markdown("**Pontos fracos (z-score mais baixo)**")
        show = weaknesses[["grupo", "métrica", "col", "valor", "z"]].copy()
        show["valor"] = show.apply(lambda r: fmt_pct(r["valor"]) if r["col"] in PERCENT_COLS else fmt_num(r["valor"]), axis=1)
        show["z"] = show["z"].map(lambda x: f"{x:+.2f}")
        st.dataframe(show.drop(columns=["col"]), hide_index=True, use_container_width=True)


    st.markdown("### Perfil táctico (radar)")
    scope_df = resumo[resumo["scope"] == scope_sel].copy()
    scores = quadrant_scores(scope_df, team_row)
    fig = plot_radar(scores, title=f"{team_sel} • {scope_sel}")
    st.pyplot(fig, clear_figure=True)

    st.markdown("### Perfil completo (Resumo)")
    st.dataframe(format_resumo_table(pd.DataFrame([team_row])), hide_index=True, use_container_width=True)
    download_button(pd.DataFrame([team_row]), f"{team_sel}_{scope_sel}_perfil.csv", "Descarregar perfil em CSV")

# ----------------------------
# Tab: Mercados
# ----------------------------
with tab_merc:
    st.subheader("Explorador de mercados por equipa")
    c1, c2, c3 = st.columns([1, 1, 1])

    with c1:
        team_sel = st.selectbox("Equipa", teams, index=0, key="m_team")
    with c2:
        scope_sel = st.selectbox("Contexto", scopes, index=0, key="m_scope")
    with c3:
        order_by = st.selectbox("Ordenar por", ["edge_vs_liga", "hit_rate", "roi_unid_por_aposta"], index=0)

    dfm = mercados[(mercados["team"] == team_sel) & (mercados["scope"] == scope_sel)].copy()
    dfm = dfm[dfm["jogos"] >= min_games].copy()

    if dfm.empty:
        st.warning("Sem linhas suficientes para os filtros actuais (aumenta ou reduz o mínimo de jogos).")
        st.stop()
    # Extras (se existirem): odds_avg -> value_est + fair odds (baseado em hit_rate), e IC de Wilson 90%
    if "odds_avg" in dfm.columns:
        dfm["odds_avg"] = pd.to_numeric(dfm["odds_avg"], errors="coerce")
        dfm["value_est"] = dfm.apply(lambda r: value_estimado(r.get("hit_rate", np.nan), r.get("odds_avg", np.nan)), axis=1)
        dfm["fair_odds_hit"] = dfm["hit_rate"].apply(fair_odds_from_hit_rate)
    else:
        dfm["odds_avg"] = np.nan
        dfm["value_est"] = np.nan
        dfm["fair_odds_hit"] = np.nan

    dfm["wilson_lo"], dfm["wilson_hi"] = zip(
        *dfm.apply(lambda r: wilson_ci(r.get("hit_rate", np.nan), r.get("jogos", np.nan), z=1.645), axis=1)
    )
    dfm["hit_rate_ic90"] = dfm.apply(
        lambda r: "—"
        if (pd.isna(r.get("hit_rate")) or pd.isna(r.get("wilson_lo")) or pd.isna(r.get("wilson_hi")))
        else f"{_to_prob(r['hit_rate'])*100:.1f}% [{r['wilson_lo']*100:.1f}–{r['wilson_hi']*100:.1f}]",
        axis=1,
    )

    # Alerta de tendência inversa (se existir no Excel)
    if "alerta_tendencia_inversa" in dfm.columns:
        dfm["alerta"] = dfm["alerta_tendencia_inversa"].apply(lambda x: "⚠️" if bool(x) and not pd.isna(x) else "")
        st.caption("⚠️ indica que a forma recente do mercado está significativamente abaixo do histórico (tendência inversa).")
    else:
        dfm["alerta"] = ""

    # Tabelas: melhores e piores por edge
    best = dfm.dropna(subset=["edge_vs_liga"]).sort_values("edge_vs_liga", ascending=False).head(8)
    worst = dfm.dropna(subset=["edge_vs_liga"]).sort_values("edge_vs_liga", ascending=True).head(8)

    cols_show = ["alerta", "market", "jogos", "hit_rate_ic90", "edge_vs_liga", "odds_avg", "value_est", "roi_unid_por_aposta"]
    cols_show = [c for c in cols_show if c in dfm.columns]

    st.markdown("### Top mercados (mais acima da média da liga)")
    view = best[cols_show].copy()
    styled = format_mercados_table(view).style
    if "value_est" in view.columns:
        styled = styled.apply(_style_value_series, subset=["value_est"])
    st.dataframe(styled, hide_index=True, use_container_width=True)

    st.markdown("### Bottom mercados (mais abaixo da média da liga)")
    view = worst[cols_show].copy()
    styled = format_mercados_table(view).style
    if "value_est" in view.columns:
        styled = styled.apply(_style_value_series, subset=["value_est"])
    st.dataframe(styled, hide_index=True, use_container_width=True)

    st.divider()
    st.markdown("### Tabela completa (filtrada)")
    dfm_sorted = dfm.sort_values(order_by, ascending=False, na_position="last")
    view = dfm_sorted[cols_show].copy() if cols_show else dfm_sorted.copy()
    styled = format_mercados_table(view).style
    if "value_est" in view.columns:
        styled = styled.apply(_style_value_series, subset=["value_est"])
    st.dataframe(styled, hide_index=True, use_container_width=True)
    download_button(dfm_sorted, f"{team_sel}_{scope_sel}_mercados.csv", "Descarregar mercados filtrados em CSV")

    st.caption("Nota: ROI só aparece quando existem odds no CSV original. Edge_vs_liga ajuda a perceber o “estilo” da equipa.")

# ----------------------------
# Tab: Forma
# ----------------------------
with tab_forma:
    st.subheader("Forma ao longo da época (médias móveis)")
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        team_sel = st.selectbox("Equipa", teams, index=0, key="f_team")
    with c2:
        metric = st.selectbox(
            "Métrica (rolling)",
            ["roll5_points", "roll5_gf", "roll5_ga", "roll5_goal_diff", "roll5_over_2_5", "roll5_under_2_5", "roll5_btts", "roll5_team_scored", "roll5_clean_sheet"],
            index=0,
        )
    with c3:
        last_n = st.slider("Últimos N jogos", 5, 25, 12)

    dft = serie[serie["team"] == team_sel].sort_values("date").copy()
    if dft.empty:
        st.warning("Sem dados na série temporal para esta equipa.")
        st.stop()

    # Chart
    chart_df = dft[["date", metric]].dropna().copy()
    kind_info = ROLLING_METRICS.get(metric, {}).get("kind")
    is_pct_metric = kind_info == "rate"
    y_raw = pd.to_numeric(chart_df[metric], errors="coerce")
    # Colunas roll5_* já são rolling pré-calculado — não têm o limite de "golos por jogo".
    # Usamos max_per_game=1e9 para desactivar o critério 3 e detectar apenas por
    # monotonia + correlação linear (série que cresce sempre de forma consistente).
    if _looks_cumulative_series(y_raw, max_per_game=1e9):
        st.warning(
            f"⚠️ `{metric}` parece conter valores cumulativos (sempre crescentes). "
            "O gráfico foi corrigido para mostrar a variação jogo-a-jogo. "
            "Para corrigir na origem, verifica se o `analisar_equipas.py` usa "
            "`rolling(5).mean()` e não `cumsum()` ao calcular esta coluna.",
            icon="⚠️",
        )
        s_diff = y_raw.diff()
        if len(y_raw) > 0 and pd.notna(y_raw.iloc[0]):
            s_diff.iloc[0] = y_raw.iloc[0]
        y_raw = s_diff.fillna(0.0)
    chart_df[metric] = y_raw
    season_mean = pd.to_numeric(chart_df[metric], errors="coerce").mean()
    plot_line_series_interactive(
        x=chart_df["date"],
        series_map={
            team_sel: chart_df[metric].to_numpy(dtype=float),
            "Média da época": np.full(len(chart_df), season_mean, dtype=float),
        },
        title=f"{team_sel} — evolução de {metric}",
        xlabel="Data",
        ylabel="%" if is_pct_metric else "Valor",
        is_pct=is_pct_metric,
    )

    # Leitura automática (heurística) do gráfico
    with st.expander("Análise ao momento da equipa", expanded=True):
        notes = form_insights(dft, metric, resumo_liga=resumo)
        for n in notes:
            st.markdown("• " + n)
        st.caption("Nota: leitura descritiva baseada em médias móveis e histórico (não é previsão). Confirma sempre contexto: adversários, ausências, calendário e fase competitiva.")

    st.markdown("### Últimos jogos")
    last = dft.sort_values("date", ascending=False).head(last_n)[
        ["date", "venue", "opponent", "gf", "ga", "result", "points", metric]
    ].copy()
    # format
    last["date"] = last["date"].dt.date.astype(str)
    if metric in {"roll5_over_2_5", "roll5_under_2_5", "roll5_btts", "roll5_team_scored", "roll5_clean_sheet"}:
        last[metric] = last[metric].apply(fmt_pct)
    else:
        last[metric] = last[metric].apply(fmt_num)
    st.dataframe(last, hide_index=True, use_container_width=True)
    download_button(last, f"{team_sel}_ultimos_{last_n}_jogos.csv", "Descarregar últimos jogos em CSV")



# ----------------------------
# Tab: Pré-jogo
# ----------------------------
with tab_prejogo:
    st.subheader(f"Pré-jogo (futuros jogos) • {league_label(league_sel)} — antever ângulos e mercados")
    st.caption("Isto usa apenas histórico (Resumo/Mercados/Forma). Não é previsão certa — é triagem de mercados e matchups.")

    left, right = st.columns([1, 1])

    with left:
        home_team = st.selectbox("Equipa da casa", teams, index=0, key="pj_home")
        away_team = st.selectbox("Equipa visitante", teams, index=1 if len(teams) > 1 else 0, key="pj_away")
        recent_weight_pct = st.slider("Peso da forma recente (%)", 0, 70, 35, 5, help="0% = só época; 35% = mistura; 70% = dá muito peso ao momento.")
        recent_n = st.slider("Forma recente: últimos N jogos (no contexto)", 3, 10, 5)
        alpha_ppg_pct = st.slider("Peso PPG (vs diff_golos)",0, 100, 60, 5,help="Mistura para o ajuste de força no 1X2: 100% = só PPG; 0% = só diff de golos.")
        min_games_pj = st.slider("Mínimo de jogos (para shortlist de mercados)", 1, 30, min_games, 1)
        prob_threshold = st.slider("Threshold para sugerir mercados (probabilidade)", 0.50, 0.80, 0.60, 0.01)

    with right:
        st.markdown("#### Importar lista de jogos (opcional)")
        st.caption("Podes carregar um CSV com colunas: `home_team,away_team` (e opcionalmente `date`). A análise será feita na **liga seleccionada**.")
        up_fix = st.file_uploader("Upload fixtures.csv", type=["csv"], key="pj_fix_upload")
        st.caption("Se fizeres upload, o dashboard gera uma tabela de ângulos por jogo e permite descarregar.")

    

    # --- Contexto manual (qualitativo) ---
    st.markdown("### Notas de contexto (qualitativo)")
    _ctx_key = f"ctx_notes::{league_sel}::{home_team}::{away_team}"
    context_notes = st.text_area(
        "Lesões, suspensões, motivação, fadiga, meteorologia, árbitro, etc. (vai para o PDF)",
        value=st.session_state.get(_ctx_key, ""),
        height=120,
    )
    st.session_state[_ctx_key] = context_notes

    with st.expander("Contexto de tabela / pressão (opcional)"):
        cta, ctb = st.columns(2)
        with cta:
            pos_home = st.number_input("Posição (Casa)", min_value=1, max_value=40, value=int(st.session_state.get("pos_home", 10)))
            pts_home = st.number_input("Pontos (Casa)", min_value=0, max_value=200, value=int(st.session_state.get("pts_home", 30)))
            imp_home = st.slider("Importância (Casa) 1–10", 1, 10, value=int(st.session_state.get("imp_home", 5)))
        with ctb:
            pos_away = st.number_input("Posição (Fora)", min_value=1, max_value=40, value=int(st.session_state.get("pos_away", 10)))
            pts_away = st.number_input("Pontos (Fora)", min_value=0, max_value=200, value=int(st.session_state.get("pts_away", 30)))
            imp_away = st.slider("Importância (Fora) 1–10", 1, 10, value=int(st.session_state.get("imp_away", 5)))

        st.session_state.update({
            "pos_home": pos_home, "pts_home": pts_home, "imp_home": imp_home,
            "pos_away": pos_away, "pts_away": pts_away, "imp_away": imp_away,
        })

    context_meta = {
        "pos_home": st.session_state.get("pos_home", ""),
        "pts_home": st.session_state.get("pts_home", ""),
        "imp_home": st.session_state.get("imp_home", ""),
        "pos_away": st.session_state.get("pos_away", ""),
        "pts_away": st.session_state.get("pts_away", ""),
        "imp_away": st.session_state.get("imp_away", ""),
    }
    conf = {}
    matchup_tables = None
    short = pd.DataFrame()
    suggestions = None
    prob_tbl = pd.DataFrame(columns=["Mercado (heurístico)", "Probabilidade"])
    eg_home = float("nan")
    eg_away = float("nan")
    reg_flags = {}

    # Single matchup
    if home_team == away_team:
        st.warning("Escolhe equipas diferentes para o pré-jogo.")
    else:
        eg_home_model, eg_away_model, dbg = expected_goals(
            resumo, serie, home_team, away_team,
            weight_recent=recent_weight_pct/100.0,
            recent_n=recent_n,
            alpha_ppg=alpha_ppg_pct/100.0
        )

        # Override manual de EG (útil quando sabes de ausências/rotação)
        eg_home, eg_away = eg_home_model, eg_away_model
        with st.expander("Ajuste manual de Expected Goals (EG)", expanded=False):
            cega, cego = st.columns(2)
            with cega:
                eg_home = st.number_input("EG Casa (ajuste)", min_value=0.0, max_value=6.0, value=float(eg_home_model) if pd.notna(eg_home_model) else 0.0, step=0.05)
            with cego:
                eg_away = st.number_input("EG Fora (ajuste)", min_value=0.0, max_value=6.0, value=float(eg_away_model) if pd.notna(eg_away_model) else 0.0, step=0.05)
            if (pd.notna(eg_home_model) and pd.notna(eg_away_model)) and (abs(float(eg_home-eg_home_model))>1e-6 or abs(float(eg_away-eg_away_model))>1e-6):
                st.caption(f"EG original: Casa {float(eg_home_model):.2f} | Fora {float(eg_away_model):.2f}  →  EG ajustado aplicado ao Poisson.")


        st.markdown("### 1) Estimativa rápida (EG) e probabilidades (Poisson)")
        if np.isnan(eg_home) or np.isnan(eg_away):
            st.error("Não consegui calcular EG (faltam dados para uma das equipas/contextos).")
        else:
            probs = poisson_probs(eg_home, eg_away, max_goals=10)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("EG Casa", f"{probs['EG Casa']:.2f}")
            c2.metric("EG Fora", f"{probs['EG Fora']:.2f}")
            c3.metric("Over 2.5", fmt_pct(probs["Over 2.5"]))
            c4.metric("BTTS Sim", fmt_pct(probs["BTTS Sim"]))

            prob_tbl = pd.DataFrame(
                {
                    "Mercado (heurístico)": ["1", "X", "2", "Over 1.5", "Over 2.5", "Under 2.5", "Under 3.5", "BTTS Sim", "Casa marca", "Fora marca"],
                    "Probabilidade": [
                        probs["1 (Casa vence)"], probs["X (Empate)"], probs["2 (Fora vence)"],
                        probs["Over 1.5"], probs["Over 2.5"], probs["Under 2.5"], probs["Under 3.5"],
                        probs["BTTS Sim"], probs["Casa marca (>=1)"], probs["Fora marca (>=1)"]
                    ],
                }
            )
            prob_tbl["Probabilidade"] = prob_tbl["Probabilidade"].apply(fmt_pct)
            st.dataframe(prob_tbl, hide_index=True, use_container_width=True)
            # Matriz de resultados prováveis (Poisson scoreline) — 0-5
            with st.expander("Matriz de resultados prováveis (Poisson 0–5)", expanded=False):
                M = poisson_score_matrix(eg_home, eg_away, max_goals=5)
                M_pct = (M * 100.0).round(2)
                st.dataframe(
                    M_pct.style.background_gradient(axis=None).format("{:.2f}%"),
                    use_container_width=True,
                )

                # Handicap Asiático (a partir da matriz 0–5)
                ah = asian_handicap_table(M)
                if ah is not None and not ah.empty:
                    view_ah = ah.copy()
                    for cc in ["P(gana)", "P(push)", "P(perde)"]:
                        view_ah[cc] = view_ah[cc].apply(lambda x: "—" if pd.isna(x) else f"{x*100:.1f}%")
                    view_ah["Fair odds"] = pd.to_numeric(view_ah["Fair odds"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
                    st.markdown("**Handicap Asiático (probabilidades e fair odds)**")
                    st.dataframe(view_ah, hide_index=True, use_container_width=True)
                st.caption("Valores em %. (Modelo Poisson independente; útil para 1X2, handicap e totais.)")


            # --- Probabilidades ao intervalo (HT) ---
            with st.expander("Probabilidades ao intervalo (HT)", expanded=False):
                serie_ht, has_ht = ensure_ht_columns(serie)
                if not has_ht:
                    st.info("Sem colunas de golos ao intervalo (HT) na 'SerieTemporal'. Se o teu CSV original tiver HTHG/HTAG, podes propagar esses campos no relatório para activar esta secção.")
                else:
                    eg_ht_home, eg_ht_away, dbg_ht = expected_goals_ht(
                        serie_ht,
                        home_team,
                        away_team,
                        weight_recent=recent_weight_pct/100.0,
                        recent_n=recent_n,
                    )
                    if np.isnan(eg_ht_home) or np.isnan(eg_ht_away):
                        st.info("Sem dados suficientes para estimar EG ao intervalo (HT) para este par (no contexto Casa/Fora).")
                    else:
                        probs_ht = poisson_probs(eg_ht_home, eg_ht_away, max_goals=8)
                        # Over 0.5 no HT
                        p00 = math.exp(-eg_ht_home) * math.exp(-eg_ht_away)
                        ht_tbl = pd.DataFrame(
                            {
                                "Mercado HT": ["HT 1", "HT X", "HT 2", "HT Over 0.5", "HT Over 1.5", "HT Under 1.5"],
                                "Probabilidade": [
                                    probs_ht["1 (Casa vence)"], probs_ht["X (Empate)"], probs_ht["2 (Fora vence)"],
                                    1.0 - p00,
                                    probs_ht["Over 1.5"],
                                    1.0 - probs_ht["Over 1.5"],
                                ],
                                "Fair odds": [
                                    1.0 / probs_ht["1 (Casa vence)"] if probs_ht["1 (Casa vence)"] > 0 else np.nan,
                                    1.0 / probs_ht["X (Empate)"] if probs_ht["X (Empate)"] > 0 else np.nan,
                                    1.0 / probs_ht["2 (Fora vence)"] if probs_ht["2 (Fora vence)"] > 0 else np.nan,
                                    1.0 / (1.0 - p00) if (1.0 - p00) > 0 else np.nan,
                                    1.0 / probs_ht["Over 1.5"] if probs_ht["Over 1.5"] > 0 else np.nan,
                                    1.0 / (1.0 - probs_ht["Over 1.5"]) if (1.0 - probs_ht["Over 1.5"]) > 0 else np.nan,
                                ],
                            }
                        )
                        ht_tbl["Probabilidade"] = ht_tbl["Probabilidade"].apply(fmt_pct)
                        ht_tbl["Fair odds"] = pd.to_numeric(ht_tbl["Fair odds"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
                        st.dataframe(ht_tbl, hide_index=True, use_container_width=True)
                        st.caption(f"EG HT estimado: Casa {eg_ht_home:.2f} | Fora {eg_ht_away:.2f}")

            # --- Mercados secundários (Poisson): Cantos e Cartões ---
            with st.expander("Mercados secundários (Poisson): Cantos e Cartões", expanded=False):
                cols_needed = {"cantos", "cantos_sofridos", "amarelos", "amarelos_sofridos"}
                missing_cols = [c for c in cols_needed if c not in resumo.columns]
                if missing_cols:
                    st.info(f"Faltam colunas no Resumo para cantos/cartões: {missing_cols}")
                else:
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Cantos (total do jogo)**")
                        lam_h, lam_a, _ = expected_count_match(resumo, home_team, away_team, "cantos", "cantos_sofridos")
                        lam_tot = lam_h + lam_a if (np.isfinite(lam_h) and np.isfinite(lam_a)) else np.nan
                        if not np.isfinite(lam_tot):
                            st.info("Sem dados suficientes para estimar cantos neste jogo.")
                        else:
                            lines = [8.5, 9.5, 10.5]
                            t = pd.DataFrame({
                                "Linha": [f"Over {x}" for x in lines],
                                "Prob.": [poisson_over_prob(lam_tot, x, max_k=60) for x in lines],
                            })
                            t["Fair odds"] = t["Prob."].apply(lambda p: (1.0/p) if (pd.notna(p) and p>0) else np.nan)
                            t["Prob."] = t["Prob."].apply(fmt_pct)
                            t["Fair odds"] = pd.to_numeric(t["Fair odds"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
                            st.caption(f"λ total cantos ≈ {lam_tot:.2f}  (Casa {lam_h:.2f} | Fora {lam_a:.2f})")
                            st.dataframe(t, hide_index=True, use_container_width=True)

                    with c2:
                        st.markdown("**Cartões (amarelos — total do jogo)**")
                        lam_h, lam_a, _ = expected_count_match(resumo, home_team, away_team, "amarelos", "amarelos_sofridos")
                        lam_tot = lam_h + lam_a if (np.isfinite(lam_h) and np.isfinite(lam_a)) else np.nan
                        if not np.isfinite(lam_tot):
                            st.info("Sem dados suficientes para estimar cartões neste jogo.")
                        else:
                            lines = [2.5, 3.5, 4.5]
                            t = pd.DataFrame({
                                "Linha": [f"Over {x}" for x in lines],
                                "Prob.": [poisson_over_prob(lam_tot, x, max_k=80) for x in lines],
                            })
                            t["Fair odds"] = t["Prob."].apply(lambda p: (1.0/p) if (pd.notna(p) and p>0) else np.nan)
                            t["Prob."] = t["Prob."].apply(fmt_pct)
                            t["Fair odds"] = pd.to_numeric(t["Fair odds"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
                            st.caption(f"λ total cartões ≈ {lam_tot:.2f}  (Casa {lam_h:.2f} | Fora {lam_a:.2f})")
                            st.dataframe(t, hide_index=True, use_container_width=True)

            with st.expander("Ver detalhes do cálculo de EG (época vs forma recente) + ajuste de força"):
                st.write("**Mix época/forma recente** (golos marcados/sofridos no contexto)")
                dshow = {
                    "Casa_gf_época": dbg.get("home_gf_season"),
                    "Casa_ga_época": dbg.get("home_ga_season"),
                    "Casa_gf_recente": dbg.get("home_gf_recent"),
                    "Casa_ga_recente": dbg.get("home_ga_recent"),
                    "Fora_gf_época": dbg.get("away_gf_season"),
                    "Fora_ga_época": dbg.get("away_ga_season"),
                    "Fora_gf_recente": dbg.get("away_gf_recent"),
                    "Fora_ga_recente": dbg.get("away_ga_recent"),
                    "Peso forma recente": dbg.get("weight_recent"),
                }
                st.json(dshow)
            
                st.write("**Ajuste de força (para 1X2)**")
                st.write(f"alpha_ppg={dbg.get('alpha_ppg', 0.6):.2f} | strength_k={dbg.get('strength_k', 0.22):.2f}")
                st.write(
                    f"Força casa={dbg.get('strength_home', 0.0):+.2f} | "
                    f"Força fora={dbg.get('strength_away', 0.0):+.2f} | "
                    f"Diferença (fora-casa)={dbg.get('diff_strength', 0.0):+.2f}"
                )
                st.write(
                    f"Factor EG casa={dbg.get('factor_home', 1.0):.3f} | "
                    f"Factor EG fora={dbg.get('factor_away', 1.0):.3f}"
                )

        st.divider()
        st.markdown("### Indicador de confiança (amostra + estabilidade)")
        conf = match_confidence(resumo, serie, home_team, away_team, recent_n=max(6, recent_n))
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        c1.metric("Confiança (0-100)", f"{conf['conf_score']:.0f}")
        c2.metric("Amostra (factor)", f"{conf['factor_amostra']:.2f}")
        c3.metric("Estabilidade (factor)", f"{conf['factor_estabilidade']:.2f}")
        c4.metric("Jogos (Casa/Fora)", f"{int(conf['jogos_casa'])}/{int(conf['jogos_fora'])}")
        st.progress(int(conf["conf_score"]))

        st.caption("Amostra penaliza poucos jogos; estabilidade baixa quando há muita variabilidade recente em golos (gf/ga).")

        st.divider()
        st.markdown("### Simulador de odds (EV) — tabela por mercado")
        if np.isnan(eg_home) or np.isnan(eg_away):
            st.info("O simulador precisa das probabilidades (EG) calculadas acima.")
        else:

            cka, ckb = st.columns(2)
            with cka:
                banca_u = st.number_input("Banca total (unidades)", min_value=0.0, max_value=1_000_000.0, value=float(st.session_state.get("bank_u", 100.0)), step=1.0)
            with ckb:
                kelly_frac = st.slider("% Kelly a usar (fraccionado)", 0, 100, int(st.session_state.get("kelly_frac_pct", 25)), 5) / 100.0
            st.session_state["bank_u"] = banca_u
            st.session_state["kelly_frac_pct"] = int(kelly_frac * 100)
            probs_for_ev = poisson_probs(eg_home, eg_away, max_goals=10)
            ev_markets = {
                "1 (Casa vence)": probs_for_ev["1 (Casa vence)"],
                "X (Empate)": probs_for_ev["X (Empate)"],
                "2 (Fora vence)": probs_for_ev["2 (Fora vence)"],
                "Over 1.5": probs_for_ev["Over 1.5"],
                "Over 2.5": probs_for_ev["Over 2.5"],
                "Under 2.5": probs_for_ev["Under 2.5"],
                "Under 3.5": probs_for_ev["Under 3.5"],
                "BTTS Sim": probs_for_ev["BTTS Sim"],
                "Casa marca (>=1)": probs_for_ev["Casa marca (>=1)"],
                "Fora marca (>=1)": probs_for_ev["Fora marca (>=1)"],
            }

            base = pd.DataFrame({
                "mercado": list(ev_markets.keys()),
                "p_modelo": list(ev_markets.values()),
                "odds": np.nan,
            })

            edited = st.data_editor(
                base,
                use_container_width=True,
                hide_index=True,
                key="poisson_odds_table",
                column_config={
                    "p_modelo": st.column_config.NumberColumn("Prob. (modelo)", format="%.3f"),
                    "odds": st.column_config.NumberColumn("Odds de mercado", format="%.2f"),
                },
            )

            extra = edited.apply(calc_ev_row, axis=1)
            out = pd.concat([edited, extra], axis=1)

            # sizing (Kelly fraccionado + banca)
            out["kelly"] = pd.to_numeric(out.get("kelly"), errors="coerce")
            out["stake_u"] = (pd.to_numeric(banca_u, errors="coerce") * float(kelly_frac) * out["kelly"].clip(lower=0)).round(3)

            view = out.copy()
            view["p_modelo"] = view["p_modelo"].apply(fmt_pct)
            view["fair_odds"] = pd.to_numeric(view["fair_odds"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
            view["odds"] = pd.to_numeric(view["odds"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
            view["EV"] = pd.to_numeric(view["EV"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f}%")
            view["kelly"] = pd.to_numeric(view["kelly"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x*100:.1f}%")
            view["stake_u"] = pd.to_numeric(view.get("stake_u"), errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f} u")

            styled = view.style
            styled = styled.apply(_style_posneg_series, subset=["EV"])
            st.dataframe(styled, hide_index=True, use_container_width=True)
            st.caption("EV e Kelly são teóricos (sem margem e sem correlação entre mercados). Usa com cautela.")
        st.divider()
        st.markdown("### 2) Pontos fortes/fracos do matchup (Casa vs Fora)")
        home = get_team_scope_row(resumo, home_team, "Casa")
        away = get_team_scope_row(resumo, away_team, "Fora")
        if home is None or away is None:
            st.error("Faltam dados de Resumo para a equipa da casa e/ou visitante no contexto Casa/Fora.")
            st.stop()

        # strengths/weaknesses by zscore in their respective scopes
        z_home = zscore_strengths(resumo[resumo["scope"] == "Casa"], home)
        z_away = zscore_strengths(resumo[resumo["scope"] == "Fora"], away)
        sh, wh = pick_strengths_weaknesses(z_home, n=4)
        sa, wa = pick_strengths_weaknesses(z_away, n=4)

                # Guardar para exportação PDF
        matchup_tables = {
            "home_strengths": sh.copy(),
            "home_weaknesses": wh.copy(),
            "away_strengths": sa.copy(),
            "away_weaknesses": wa.copy(),
        }

        colA, colB = st.columns(2)
        with colA:
            st.markdown(f"#### {home_team} (Casa)")
            render_result_badges(recent_results_seq(serie, home_team, "H", n=5), label="Últimos 5 (Casa)")
            # render_kpis(home)  # removido aqui (ver tab Confronto)
            st.markdown("**Forças (vs liga em Casa)**")
            t = sh[["grupo", "métrica", "col", "valor", "z"]].copy()
            t["valor"] = t.apply(lambda r: fmt_pct(r["valor"]) if r["col"] in PERCENT_COLS else fmt_num(r["valor"]), axis=1)
            t["z"] = t["z"].map(lambda x: f"{x:+.2f}")
            st.dataframe(t.drop(columns=["col"]), hide_index=True, use_container_width=True)
            st.markdown("**Fraquezas (vs liga em Casa)**")
            t = wh[["grupo", "métrica", "col", "valor", "z"]].copy()
            t["valor"] = t.apply(lambda r: fmt_pct(r["valor"]) if r["col"] in PERCENT_COLS else fmt_num(r["valor"]), axis=1)
            t["z"] = t["z"].map(lambda x: f"{x:+.2f}")
            st.dataframe(t.drop(columns=["col"]), hide_index=True, use_container_width=True)

        with colB:
            st.markdown(f"#### {away_team} (Fora)")
            render_result_badges(recent_results_seq(serie, away_team, "A", n=5), label="Últimos 5 (Fora)")
            # render_kpis(away)  # removido aqui (ver tab Confronto)
            st.markdown("**Forças (vs liga fora)**")
            t = sa[["grupo", "métrica", "col", "valor", "z"]].copy()
            t["valor"] = t.apply(lambda r: fmt_pct(r["valor"]) if r["col"] in PERCENT_COLS else fmt_num(r["valor"]), axis=1)
            t["z"] = t["z"].map(lambda x: f"{x:+.2f}")
            st.dataframe(t.drop(columns=["col"]), hide_index=True, use_container_width=True)
            st.markdown("**Fraquezas (vs liga fora)**")
            t = wa[["grupo", "métrica", "col", "valor", "z"]].copy()
            t["valor"] = t.apply(lambda r: fmt_pct(r["valor"]) if r["col"] in PERCENT_COLS else fmt_num(r["valor"]), axis=1)
            t["z"] = t["z"].map(lambda x: f"{x:+.2f}")
            st.dataframe(t.drop(columns=["col"]), hide_index=True, use_container_width=True)

        
        st.markdown("### 2.5) Forma comparada (contexto Casa/Fora)")
        # Flags de regressão à média (rollN vs mean±k·std)
        reg_flags = matchup_regression_flags(serie, home_team, away_team, last_n=recent_n, k=1.5)

        with st.expander("Comparação de forma (rolling no contexto Casa/Fora)", expanded=False):

            kind_opts = {
                "Ataque vs Defesa (GF Casa vs GA Fora)": "gf_vs_ga",
                "Golos marcados (rolling)": "gf",
                "Golos sofridos (rolling)": "ga",
                "Total de golos (rolling)": "total_goals",
                "Over 2.5 (taxa rolling)": "over25",
                "BTTS (taxa rolling)": "btts",
            }

            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                sel_label = st.selectbox("Métrica", list(kind_opts.keys()), index=0, key="pj_form_compare_kind")
                kind = kind_opts[sel_label]
            with c2:
                x_mode = st.radio(
                    "Eixo X",
                    ["Últimos jogos (ordem)", "Datas reais"],
                    horizontal=True,
                    key="pj_form_compare_xmode",
                )
            with c3:
                vis_n = st.slider("Zoom (últimos jogos)", 6, 30, value=max(12, int(recent_n)), key="pj_form_compare_visn")

            # Construir séries (rolling) no contexto Casa/Fora
            if kind == "gf_vs_ga":
                s_home = form_series_context(serie, home_team, "H", "gf", roll_n=recent_n)
                s_away = form_series_context(serie, away_team, "A", "ga", roll_n=recent_n)
                title = f"Ataque vs Defesa — {home_team} (GF Casa) vs {away_team} (GA Fora)"
                is_pct = False
                ylabel = "Golos (média móvel)"
            else:
                s_home = form_series_context(serie, home_team, "H", kind, roll_n=recent_n)
                s_away = form_series_context(serie, away_team, "A", kind, roll_n=recent_n)
                is_pct = kind in {"over25", "btts"}
                ylabel = "% (média móvel)" if is_pct else "Valor (média móvel)"
                title_map = {
                    "gf": "Golos marcados (rolling)",
                    "ga": "Golos sofridos (rolling)",
                    "total_goals": "Total de golos (rolling)",
                    "over25": "Over 2.5 (taxa rolling)",
                    "btts": "BTTS (taxa rolling)",
                }
                title = title_map.get(kind, sel_label)

            if (s_home.empty) and (s_away.empty):
                st.info("Sem dados suficientes para comparar a forma no contexto (Casa/Fora).")
            else:
                # Escala para percentagem quando aplicável
                if is_pct:
                    if not s_home.empty:
                        s_home = s_home.copy()
                        s_home["value"] = s_home["value"] * 100.0
                    if not s_away.empty:
                        s_away = s_away.copy()
                        s_away["value"] = s_away["value"] * 100.0

                if x_mode.startswith("Últimos"):
                    n = int(vis_n)
                    x = list(range(1, n + 1))
                    y_home = _pad_left_tail(s_home["value"].to_numpy() if not s_home.empty else np.array([]), n)
                    y_away = _pad_left_tail(s_away["value"].to_numpy() if not s_away.empty else np.array([]), n)

                    plot_dual_series_matplotlib(
                        x,
                        {f"{home_team} (Casa)": y_home, f"{away_team} (Fora)": y_away},
                        title=title,
                        xlabel="Últimos jogos no contexto (mais antigo → mais recente)",
                        ylabel=ylabel,
                        is_pct=is_pct,
                    )
                else:
                    # Datas reais: útil para ver 'quando' aconteceu, mas pode ficar segmentado (Casa/Fora não partilham datas)
                    df_plot = pd.merge(
                        s_home.rename(columns={"value": f"{home_team} (Casa)"}),
                        s_away.rename(columns={"value": f"{away_team} (Fora)"}),
                        on="date",
                        how="outer",
                    ).sort_values("date")
                    df_plot = df_plot.tail(int(vis_n)).copy()

                    x = df_plot["date"].to_numpy()
                    y_home = pd.to_numeric(df_plot.get(f"{home_team} (Casa)"), errors="coerce").to_numpy(dtype=float)
                    y_away = pd.to_numeric(df_plot.get(f"{away_team} (Fora)"), errors="coerce").to_numpy(dtype=float)

                    plot_dual_series_matplotlib(
                        x,
                        {f"{home_team} (Casa)": y_home, f"{away_team} (Fora)": y_away},
                        title=title,
                        xlabel="Data",
                        ylabel=ylabel,
                        is_pct=is_pct,
                    )

                # Mini-resumo (último vs anterior)
                n = int(vis_n)
                yh = _pad_left_tail(s_home["value"].to_numpy() if not s_home.empty else np.array([]), n)
                ya = _pad_left_tail(s_away["value"].to_numpy() if not s_away.empty else np.array([]), n)
                lh, ph, dh = last_prev_delta(yh)
                la, pa, da = last_prev_delta(ya)

                df_sum = pd.DataFrame(
                    {
                        "Equipa": [f"{home_team} (Casa)", f"{away_team} (Fora)"],
                        "Último": [lh, la],
                        "Anterior": [ph, pa],
                        "Δ": [dh, da],
                    }
                )

                if is_pct:
                    df_sum["Último"] = df_sum["Último"].map(lambda x: "—" if pd.isna(x) else f"{x:.0f}%")
                    df_sum["Anterior"] = df_sum["Anterior"].map(lambda x: "—" if pd.isna(x) else f"{x:.0f}%")
                    df_sum["Δ"] = df_sum["Δ"].map(lambda x: "—" if pd.isna(x) else f"{x:+.0f}%")
                else:
                    df_sum["Último"] = df_sum["Último"].map(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
                    df_sum["Anterior"] = df_sum["Anterior"].map(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
                    df_sum["Δ"] = df_sum["Δ"].map(lambda x: "—" if pd.isna(x) else f"{x:+.2f}")

                st.dataframe(df_sum, hide_index=True, use_container_width=True)
                st.caption("Dica: 'Últimos jogos (ordem)' dá uma leitura mais comparável quando as datas não coincidem entre Casa e Fora.")


            # Mostrar tags de regressão para mercados-chave
            st.markdown("**Alertas de regressão à média (heurístico)**")
            render_regression_tag_line("Over 2.5", "over25", reg_flags, home_team, away_team)
            render_regression_tag_line("BTTS", "btts", reg_flags, home_team, away_team)
            render_regression_tag_line("Marca (>=1)", "scored", reg_flags, home_team, away_team)
            render_regression_tag_line("Total de golos", "total_goals", reg_flags, home_team, away_team)
            st.caption("⚡ = forma recente muito acima da média (pode regredir). 📉 = muito abaixo (pode recuperar).")

        st.divider()
        st.markdown("### 3) Shortlist de mercados baseada em 'edge' histórico (Casa vs Fora)")
        short = shortlist_markets(mercados, home_team, away_team, min_games=min_games_pj)
        if short.empty:
            st.info("Sem dados suficientes para shortlist (revê o mínimo de jogos ou confirma se a folha 'Mercados' tem linhas para essas equipas).")
        else:
            top = short.head(12).copy()
            # Sinal combinado (edge + Poisson + value quando existir)
            if not (np.isnan(eg_home) or np.isnan(eg_away)):
                _pb_sig = poisson_probs(eg_home, eg_away, max_goals=10)
            else:
                _pb_sig = {}
            top["p_poisson"] = top["market"].apply(lambda m: poisson_prob_for_market(m, _pb_sig))

            # value médio (se houver value_est_* já vindo do Excel)
            if ("value_est_casa" in top.columns) or ("value_est_fora" in top.columns):
                v1 = pd.to_numeric(top.get("value_est_casa", np.nan), errors="coerce")
                v2 = pd.to_numeric(top.get("value_est_fora", np.nan), errors="coerce")
                top["value_est_media"] = pd.concat([v1, v2], axis=1).mean(axis=1)
            else:
                top["value_est_media"] = np.nan
            top["sinal"] = top.apply(shortlist_signal_row, axis=1)
            top["semaforo_edge"] = top["edge_media"].apply(edge_semaforo)

            # Regressão à média (roll recente vs média da época)
            top["regressao"] = top["market"].apply(lambda m: regression_icon_for_market(m, reg_flags))

            # IC de Wilson (90%) para hit rates Casa/Fora
            top["wilson_lo_casa"], top["wilson_hi_casa"] = zip(*top.apply(lambda r: wilson_ci(r.get("hit_rate_casa", np.nan), r.get("jogos_casa", np.nan), z=1.645), axis=1))
            top["wilson_lo_fora"], top["wilson_hi_fora"] = zip(*top.apply(lambda r: wilson_ci(r.get("hit_rate_fora", np.nan), r.get("jogos_fora", np.nan), z=1.645), axis=1))

            top["hit_casa_ic90"] = top.apply(
                lambda r: "—" if pd.isna(r.get("hit_rate_casa")) or pd.isna(r.get("wilson_lo_casa"))
                else f"{_to_prob(r['hit_rate_casa'])*100:.1f}% [{r['wilson_lo_casa']*100:.1f}–{r['wilson_hi_casa']*100:.1f}]",
                axis=1,
            )
            top["hit_fora_ic90"] = top.apply(
                lambda r: "—" if pd.isna(r.get("hit_rate_fora")) or pd.isna(r.get("wilson_lo_fora"))
                else f"{_to_prob(r['hit_rate_fora'])*100:.1f}% [{r['wilson_lo_fora']*100:.1f}–{r['wilson_hi_fora']*100:.1f}]",
                axis=1,
            )

            # Tabela (com value/odds se existirem)
            cols = [
                "alerta",
                "semaforo_edge",
                "regressao",
                "market",
                "edge_vs_liga_casa", "edge_vs_liga_fora", "edge_media",
                "hit_casa_ic90", "hit_fora_ic90",
                "jogos_casa", "jogos_fora",
            ]
            for c in ["odds_avg_casa", "odds_avg_fora", "value_est_casa", "value_est_fora"]:
                if c in top.columns:
                    cols.append(c)
            cols += ["roi_unid_por_aposta_casa", "roi_unid_por_aposta_fora"]

            show = top[cols].copy()

            # formatação leve
            for c in ["edge_vs_liga_casa", "edge_vs_liga_fora", "edge_media"]:
                if c in show.columns:
                    show[c] = show[c].apply(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f} pp")
            if "p_poisson" in show.columns:
                show["p_poisson"] = pd.to_numeric(show["p_poisson"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x*100:.1f}%")
            for c in ["odds_avg_casa", "odds_avg_fora"]:
                if c in show.columns:
                    show[c] = pd.to_numeric(show[c], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
            for c in ["value_est_casa", "value_est_fora"]:
                if c in show.columns:
                    show[c] = pd.to_numeric(show[c], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f}%")
            for c in ["roi_unid_por_aposta_casa", "roi_unid_por_aposta_fora"]:
                if c in show.columns:
                    show[c] = show[c].apply(fmt_roi)

            styled = show.style
            for c in ["value_est_casa", "value_est_fora"]:
                if c in show.columns:
                    styled = styled.apply(_style_value_series, subset=[c])
            st.dataframe(styled, hide_index=True, use_container_width=True)
            st.caption("Regressão: ⚡ forma muito acima da média (pode regredir); 📉 muito abaixo (pode recuperar).")


            # Odds por mercado (input) → fair odds + value estimado (por linha)
            st.markdown("#### Odds por mercado (fair odds e value)")
            calc_tbl = top[["market"]].copy()
            calc_tbl["p_hist"] = top[["hit_rate_casa", "hit_rate_fora"]].mean(axis=1).apply(_to_prob)
            calc_tbl["fair_odds"] = calc_tbl["p_hist"].apply(lambda p: fair_odds_from_hit_rate(p))

            if ("odds_avg_casa" in top.columns) and ("odds_avg_fora" in top.columns):
                calc_tbl["odds"] = pd.to_numeric(top[["odds_avg_casa", "odds_avg_fora"]].mean(axis=1), errors="coerce")
            else:
                calc_tbl["odds"] = np.nan

            edited = st.data_editor(
                calc_tbl,
                use_container_width=True,
                hide_index=True,
                key="odds_editor_shortlist",
            )

            edited["value_est"] = edited.apply(lambda r: value_estimado(r.get("p_hist", np.nan), r.get("odds", np.nan)), axis=1)
            view = edited.copy()
            view["p_hist"] = view["p_hist"].apply(lambda x: "—" if pd.isna(x) else f"{x*100:.1f}%")
            view["fair_odds"] = view["fair_odds"].apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
            view["odds"] = pd.to_numeric(view["odds"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
            view["value_est"] = view["value_est"].apply(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f}%")
            styled2 = view.style.apply(_style_value_series, subset=["value_est"])
            st.dataframe(styled2, hide_index=True, use_container_width=True)

        st.divider()
        st.markdown("### 4) Sugestões automáticas")
        suggestions = []
        if not (np.isnan(eg_home) or np.isnan(eg_away)):
            probs = poisson_probs(eg_home, eg_away, max_goals=10)
            # prob-based suggestions
            mapping = [
                ("Over 1.5", "Over 1.5"),
                ("Over 2.5", "Over 2.5"),
                ("Under 2.5", "Under 2.5"),
                ("Under 3.5", "Under 3.5"),
                ("BTTS Sim", "BTTS Sim"),
                ("Casa marca (>=1)", "Casa marca (>=1)"),
                ("Fora marca (>=1)", "Fora marca (>=1)"),
            ]
            for label, key in mapping:
                p = probs.get(key, np.nan)
                if not np.isnan(p) and p >= prob_threshold:
                    suggestions.append(f"• **{label}** — prob. ~ {fmt_pct(p)} (modelo Poisson simples).")

        # edge reinforcement
        if not short.empty:
            # pick a few robust ones
            robust = short.dropna(subset=["edge_media"]).head(5)
            for _, r in robust.iterrows():
                em = r.get("edge_media", np.nan)
                if pd.notna(em) and abs(em) >= 0.03:  # 3 pp
                    suggestions.append(f"• **{r['market']}** — edge média vs liga: {em*100:+.1f} pp (Casa+Fora).")

        if suggestions:
            for s in suggestions[:12]:
                st.write(s)
        else:
            st.info("Não surgiram sugestões fortes com os thresholds actuais. Ajusta o threshold, o peso da forma recente, ou consulta a shortlist de mercados.")

        st.divider()

        # 5) 🎯 Trading Lay (degradação graciosa: só aparece se existir no Excel)
        if lay_cand is not None and not lay_cand.empty:
            st.markdown("### 5) 🎯 Trading Lay")
            st.caption("Cenários onde o evento é raro (tendem a ser melhores candidatos a lay). Verde = raro; vermelho = frequente.")

            lay_topn_pj = st.slider("Top N cenários (Lay) — para este jogo", 3, 15, 8, 1, key="pj_lay_topn")
            colL, colR = st.columns(2)
            with colL:
                st.markdown(f"#### {home_team} (Casa)")
                d1 = lay_candidates_for_team(lay_cand, home_team, "Casa", top_n=lay_topn_pj)
                render_lay_pills(d1, max_pills=min(6, lay_topn_pj))
                _v, _sty = lay_table_view(d1)
                st.dataframe(_sty, hide_index=True, use_container_width=True)
            with colR:
                st.markdown(f"#### {away_team} (Fora)")
                d2 = lay_candidates_for_team(lay_cand, away_team, "Fora", top_n=lay_topn_pj)
                render_lay_pills(d2, max_pills=min(6, lay_topn_pj))
                _v, _sty = lay_table_view(d2)
                st.dataframe(_sty, hide_index=True, use_container_width=True)

            conv = lay_convergent_table(d1, d2, top_n=lay_topn_pj)
            if conv is not None and not conv.empty:
                st.markdown("**Cenários convergentes (bom sinal dos dois lados)**")
                st.dataframe(conv, hide_index=True, use_container_width=True)

        st.divider()
        st.markdown("### Tracker de apostas (sessão)")
        st.caption("Regista apostas desta sessão (não persiste quando fechas a app). Útil para controlo rápido de P&L.")

        if "bets_log" not in st.session_state:
            st.session_state["bets_log"] = []

        with st.expander("Abrir tracker", expanded=False):
            cta, ctb, ctc = st.columns([2, 1, 1])
            with cta:
                bet_market = st.text_input("Mercado", value="", key="bet_market_in")
            with ctb:
                bet_odds = st.number_input("Odds", min_value=1.01, max_value=100.0, value=2.00, step=0.01, key="bet_odds_in")
            with ctc:
                bet_stake = st.number_input("Stake (u)", min_value=0.0, max_value=100000.0, value=1.00, step=0.25, key="bet_stake_in")

            ctd, cte = st.columns([1, 3])
            with ctd:
                if st.button("Adicionar", key="bet_add_btn"):
                    if str(bet_market).strip():
                        st.session_state["bets_log"].append({
                            "jogo": f"{home_team} vs {away_team}",
                            "mercado": str(bet_market).strip(),
                            "odds": float(bet_odds),
                            "stake_u": float(bet_stake),
                            "estado": "pendente",
                        })
            with cte:
                if st.button("Limpar tracker (sessão)", key="bet_clear_btn"):
                    st.session_state["bets_log"] = []

            log_df = pd.DataFrame(st.session_state["bets_log"])
            if log_df.empty:
                st.info("Ainda não há apostas registadas nesta sessão.")
            else:
                if "estado" not in log_df.columns:
                    log_df["estado"] = "pendente"
                edited = st.data_editor(
                    log_df,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "estado": st.column_config.SelectboxColumn("estado", options=["pendente", "ganhou", "perdeu", "void"])
                    },
                    key="bets_editor",
                )
                edited["pnl_u"] = edited.apply(pnl_row, axis=1)
                pnl_total = float(pd.to_numeric(edited["pnl_u"], errors="coerce").fillna(0).sum())
                stake_total = float(pd.to_numeric(edited["stake_u"], errors="coerce").fillna(0).sum())
                roi = (pnl_total / stake_total) if stake_total > 0 else float("nan")
                st.session_state["bets_log"] = edited.drop(columns=["pnl_u"], errors="ignore").to_dict("records")
                c1, c2, c3 = st.columns(3)
                c1.metric("Stake total (u)", f"{stake_total:.2f}")
                c2.metric("P&L (u)", f"{pnl_total:+.2f}")
                c3.metric("ROI", "—" if pd.isna(roi) else f"{roi*100:+.1f}%")
                view = edited.copy()
                view["odds"] = pd.to_numeric(view["odds"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
                view["stake_u"] = pd.to_numeric(view["stake_u"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
                view["pnl_u"] = pd.to_numeric(view["pnl_u"], errors="coerce").apply(lambda x: "—" if pd.isna(x) else f"{x:+.2f}")
                st.dataframe(view, hide_index=True, use_container_width=True)

        st.markdown("### Exportar (PDF)")
        try:
            settings_pdf = {
                "peso_forma": recent_weight_pct,
                "recent_n": recent_n,
                "min_games": min_games_pj,
                "prob_threshold": prob_threshold,
                "alpha_ppg": alpha_ppg_pct,
            }
            league_txt = league_label(league_sel)
            pdf_bytes = build_prejogo_pdf(
                league_label_txt=league_txt,
                home_team=home_team,
                away_team=away_team,
                settings=settings_pdf,
                eg_home=eg_home,
                eg_away=eg_away,
                probs_table=prob_tbl.copy(),
                conf=conf,
                matchup_tables=matchup_tables,
                shortlist_df=short,
                suggestions=suggestions,
                context_notes=context_notes,
                context_meta=context_meta,
            )
            fname = f"prejogo_{league_sel}_{home_team}_vs_{away_team}.pdf".replace(" ", "_")
            st.download_button("Descarregar PDF desta análise", data=pdf_bytes, file_name=fname, mime="application/pdf")
        except Exception as e:
            st.warning(f"Não consegui gerar o PDF: {e}")

        if up_fix is not None:
            try:
                fx = pd.read_csv(up_fix)
            except Exception:
                st.error("Não consegui ler o CSV. Confirma se está em formato CSV e com colunas home_team,away_team.")
                st.stop()
            fx_cols = {c.lower(): c for c in fx.columns}
            if "home_team" not in fx_cols or "away_team" not in fx_cols:
                st.error("O CSV precisa de ter colunas: home_team, away_team (e opcionalmente date).")
                st.stop()
            fx = fx.rename(columns={fx_cols["home_team"]: "home_team", fx_cols["away_team"]: "away_team"})
            if "date" in fx_cols:
                fx = fx.rename(columns={fx_cols["date"]: "date"})
            rows = []
            for _, r in fx.iterrows():
                ht = str(r["home_team"]).strip()
                at = str(r["away_team"]).strip()
                if ht not in teams or at not in teams or ht == at:
                    continue
                eg_h, eg_a, _ = expected_goals(resumo, serie, ht, at, weight_recent=recent_weight_pct/100.0, recent_n=recent_n, alpha_ppg=alpha_ppg_pct/100.0)
                if np.isnan(eg_h) or np.isnan(eg_a):
                    continue
                pb = poisson_probs(eg_h, eg_a, max_goals=10)
                short_fx = shortlist_markets(mercados, ht, at, min_games=min_games_pj).head(3)
                short_txt = "; ".join([f"{x} ({y*100:+.1f}pp)" for x, y in zip(short_fx["market"].tolist(), short_fx["edge_media"].tolist())]) if not short_fx.empty else ""
                rows.append({
                    "home_team": ht,
                    "away_team": at,
                    "EG_casa": pb["EG Casa"],
                    "EG_fora": pb["EG Fora"],
                    "P_Over2.5": pb["Over 2.5"],
                    "P_BTTS": pb["BTTS Sim"],
                    "P_1": pb["1 (Casa vence)"],
                    "P_X": pb["X (Empate)"],
                    "P_2": pb["2 (Fora vence)"],
                    "Top_edges": short_txt,
                })
            out = pd.DataFrame(rows)
            if out.empty:
                st.warning("Não consegui gerar tabela — confirma nomes das equipas (exactos como no relatório) e colunas do CSV.")
            else:
                st.markdown("### Lista de jogos (análise rápida)")
                disp = out.copy()
                for c in ["EG_casa", "EG_fora"]:
                    disp[c] = disp[c].map(lambda x: f"{x:.2f}")
                for c in ["P_Over2.5", "P_BTTS", "P_1", "P_X", "P_2"]:
                    disp[c] = disp[c].map(fmt_pct)
                st.dataframe(disp, hide_index=True, use_container_width=True)
                download_button(out, "prejogo_fixtures_analise.csv", "Descarregar análise dos jogos em CSV")

# ----------------------------
# Tab: Scanner (Multi-liga)
# ----------------------------
# ----------------------------
# Tab: 🎯 Trading Lay
# ----------------------------
with tab_lay:
    st.subheader("🎯 Trading Lay — cenários improváveis (bons candidatos a lay)")

    if lay_cand is None or lay_cand.empty:
        st.warning("Não encontrei dados de Trading Lay no Excel. O dashboard continua a funcionar normalmente, mas esta tab precisa das sheets `Lay_Candidatos`/`Lay_Top`.")
        st.code("python analisar_equipas.py --lay\n# ou\npython analisar_equipas_lay.py --lay", language="bash")
    else:
        st.caption("Verde = evento raro (bom para lay). Vermelho = evento frequente (fraco para lay).")

        # 1) Candidatos por equipa
        st.markdown("## 1) Candidatos lay por equipa")
        c1, c2, c3 = st.columns([1.2, 1.0, 0.8])
        with c1:
            lay_team = st.selectbox("Equipa", teams, index=0, key="lay_team")
        with c2:
            lay_scope = st.selectbox("Contexto", ["Total", "Casa", "Fora"], index=1, key="lay_scope")
        with c3:
            lay_topn = st.slider("Top N", 3, 20, 10, 1, key="lay_topn")

        d_team = lay_candidates_for_team(lay_cand, lay_team, lay_scope, top_n=lay_topn)
        render_lay_pills(d_team, max_pills=min(8, lay_topn), title="Cenários mais improváveis")
        _view, _styler = lay_table_view(d_team)
        st.dataframe(_styler, hide_index=True, use_container_width=True)

        st.divider()

        # 2) Scanner multi-equipa
        st.markdown("## 2) Scanner multi-equipa (ranking por cenário)")
        s1, s2, s3 = st.columns([1.4, 1.0, 0.8])
        scen_opts = sorted(lay_cand["cenario_lay"].dropna().astype(str).unique().tolist())
        with s1:
            scen_sel = st.selectbox("Cenário", scen_opts, index=0, key="lay_scan_scen")
        with s2:
            sc_sel = st.selectbox("Contexto", ["Total", "Casa", "Fora"], index=1, key="lay_scan_scope")
        with s3:
            top_scan = st.slider("Top (equipas)", 5, 50, 20, 5, key="lay_scan_top")

        dscan = lay_cand[(lay_cand["scope"] == sc_sel) & (lay_cand["cenario_lay"] == scen_sel)].copy()
        if dscan.empty:
            st.info("Sem linhas para este cenário/contexto (confirma mínimo de jogos do --lay).")
        else:
            dscan = dscan.sort_values(["lay_score", "hit_rate"], ascending=[False, True]).head(int(top_scan))
            dscan["IC"] = dscan.apply(
                lambda r: "—" if pd.isna(r.get("wilson_lo")) or pd.isna(r.get("wilson_hi"))
                else f"{float(r['wilson_lo'])*100:.0f}%–{float(r['wilson_hi'])*100:.0f}%",
                axis=1,
            )
            dscan["flag"] = dscan.get("flag_candidato", False).apply(lambda x: "✅" if bool(x) else "")
            view = dscan[["team", "jogos", "hit_rate", "IC", "edge_vs_liga", "lay_score", "flag"]].copy()
            view["hit_rate"] = view["hit_rate"].apply(lambda x: "—" if pd.isna(x) else f"{x*100:.1f}%")
            view["edge_vs_liga"] = view["edge_vs_liga"].apply(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f} pp")
            view["lay_score"] = view["lay_score"].apply(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
            st.dataframe(view.style.apply(_style_lay_hit_rate_series, subset=["hit_rate"]), hide_index=True, use_container_width=True)

        st.divider()

        # 3) Comparativo Casa vs Fora
        st.markdown("## 3) Comparativo Casa vs Fora (matchup)")
        p1, p2, p3 = st.columns([1.2, 1.2, 0.8])
        with p1:
            cmp_home = st.selectbox("Casa (equipa)", teams, index=0, key="lay_cmp_home")
        with p2:
            cmp_away = st.selectbox("Fora (equipa)", teams, index=1 if len(teams) > 1 else 0, key="lay_cmp_away")
        with p3:
            cmp_topn = st.slider("Top N (por lado)", 3, 20, 8, 1, key="lay_cmp_topn")

        d_home = lay_candidates_for_team(lay_cand, cmp_home, "Casa", top_n=cmp_topn)
        d_away = lay_candidates_for_team(lay_cand, cmp_away, "Fora", top_n=cmp_topn)

        a, b = st.columns(2)
        with a:
            st.markdown(f"### {cmp_home} (Casa)")
            render_lay_pills(d_home, max_pills=min(6, cmp_topn))
            _v, _sty = lay_table_view(d_home)
            st.dataframe(_sty, hide_index=True, use_container_width=True)
        with b:
            st.markdown(f"### {cmp_away} (Fora)")
            render_lay_pills(d_away, max_pills=min(6, cmp_topn))
            _v, _sty = lay_table_view(d_away)
            st.dataframe(_sty, hide_index=True, use_container_width=True)

        conv = lay_convergent_table(d_home, d_away, top_n=cmp_topn)
        st.markdown("### Cenários convergentes (bom sinal dos dois lados)")
        if conv.empty:
            st.info("Não há cenários convergentes nos Top N actuais.")
        else:
            st.dataframe(conv, hide_index=True, use_container_width=True)

        st.divider()

        # 4) Export CSV
        st.markdown("## 4) Export CSV")
        st.caption("Descarrega os candidatos lay desta liga (podes filtrar por contexto e/ou cenário).")
        e1, e2 = st.columns([1, 2])
        with e1:
            exp_scope = st.selectbox("Contexto (export)", ["Todos", "Total", "Casa", "Fora"], index=0, key="lay_exp_scope")
        with e2:
            exp_scen = st.selectbox("Cenário (export)", ["Todos"] + scen_opts, index=0, key="lay_exp_scen")

        dexp = lay_cand.copy()
        if exp_scope != "Todos":
            dexp = dexp[dexp["scope"] == exp_scope]
        if exp_scen != "Todos":
            dexp = dexp[dexp["cenario_lay"] == exp_scen]
        download_button(dexp, f"lay_candidatos_{league_sel}.csv", "Descarregar candidatos lay (CSV)")

with tab_scanner:
    st.subheader("Scanner (Multi-liga) — equipas mais fortes por mercado")
    st.caption("Baseado em edge_vs_liga e hit_rate (histórico). Útil para descobrir padrões por equipa em qualquer liga.")

    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])
    with c1:
        league_opt = ["Todas"] + sorted(mercados_all["league"].dropna().unique().tolist())
        lg = st.selectbox("Liga", league_opt, index=0)
    with c2:
        scope_opt = ["Total", "Casa", "Fora"]
        sc = st.selectbox("Contexto", scope_opt, index=0)
    with c3:
        grp = st.selectbox("Grupo de mercado", list(MARKET_GROUPS.keys()), index=0)
    with c4:
        min_g = st.slider("Mín. jogos", 1, 30, 8, 1)
    with c5:
        topn = st.slider("Top N por equipa", 1, 10, 3, 1)

    # filtrar base
    df = mercados_all.copy()
    if lg != "Todas":
        df = df[df["league"] == lg]
    df = df[df["scope"] == sc]
    df = df[df["jogos"] >= min_g]

    # filtrar por grupo (match por substring para aguentar nomes diferentes)
    wanted = [x.lower() for x in MARKET_GROUPS[grp]]
    df = df[df["market"].astype(str).str.lower().apply(lambda m: any(w in m for w in wanted))].copy()

    if df.empty:
        st.warning("Sem resultados com estes filtros. Ajusta liga/grupo/min jogos.")
        st.stop()

    # score: edge ponderado por amostra + bónus de hit_rate
    # (podes alterar pesos depois)
    df["edge"] = pd.to_numeric(df.get("edge_vs_liga"), errors="coerce")
    df["hit"] = pd.to_numeric(df.get("hit_rate"), errors="coerce")
    df["w"] = np.sqrt(pd.to_numeric(df["jogos"], errors="coerce").clip(lower=1))
    df["score"] = df["edge"].fillna(0) * df["w"] + 0.15 * (df["hit"].fillna(0) - 0.5)

    # Pivot: 1 linha por equipa, 1 coluna por mercado (percentagens)
    df_p = df.copy()
    
    # opcional: manter só os "topn" mercados por equipa antes de pivotar (para não ter 50 colunas)
    df_p = df_p.sort_values(["league", "team", "score"], ascending=[True, True, False])
    df_p = df_p.groupby(["league", "team"], as_index=False).head(topn).copy()
    
    # pivot em hit_rate
    pivot_hit = df_p.pivot_table(
        index=["league", "team"],
        columns="market",
        values="hit_rate",
        aggfunc="mean"
    )
    
    # pivot em edge (opcional, útil para ordenar por "diferença vs liga")
    pivot_edge = df_p.pivot_table(
        index=["league", "team"],
        columns="market",
        values="edge_vs_liga",
        aggfunc="mean"
    )
    
    # escolher o que mostrar (hit_rate por defeito)
    mode = st.radio("Mostrar", ["hit_rate (%)", "edge_vs_liga (pp)"], horizontal=True, index=0)
    
    if mode == "hit_rate (%)":
        show = pivot_hit.reset_index()
        # formatar percentagens
        for c in show.columns:
            if c not in ["league", "team"]:
                show[c] = (pd.to_numeric(show[c], errors="coerce") * 100).round(1)
    else:
        show = pivot_edge.reset_index()
        # formatar em pontos percentuais
        for c in show.columns:
            if c not in ["league", "team"]:
                show[c] = show[c].apply(lambda x: "—" if pd.isna(x) else f"{x*100:+.1f} pp")
    
    st.markdown("### Resultados (uma coluna por mercado)")
    st.dataframe(show, use_container_width=True, hide_index=True)
    
    # export (sem formatação para manter números)
    csv_base = pivot_hit.reset_index().to_csv(index=False).encode("utf-8") if mode == "hit_rate (%)" else pivot_edge.reset_index().to_csv(index=False).encode("utf-8")
    st.download_button(
        "Descarregar resultados (CSV)",
        data=csv_base,
        file_name=f"scanner_pivot_{grp.replace(' ','_')}_{lg}_{sc}.csv".replace(" ", "_"),
        mime="text/csv"
    )

# ----------------------------
# Tab: Confronto
# ----------------------------
with tab_confronto:
    st.subheader(f"Confronto (Casa vs Fora) • {league_label(league_sel)}")
    col1, col2 = st.columns(2)
    idx_home_con = teams.index(st.session_state.get("pj_home")) if st.session_state.get("pj_home") in teams else 0
    idx_away_con = teams.index(st.session_state.get("pj_away")) if st.session_state.get("pj_away") in teams else (1 if len(teams) > 1 else 0)
    with col1:
        home_team = st.selectbox("Equipa da casa", teams, index=idx_home_con, key="home_team")
    with col2:
        away_team = st.selectbox("Equipa visitante", teams, index=idx_away_con, key="away_team")

    home = get_team_scope_row(resumo, home_team, "Casa")
    away = get_team_scope_row(resumo, away_team, "Fora")
    if home is None or away is None:
        st.error("Faltam dados de Resumo para a equipa da casa e/ou visitante no contexto Casa/Fora.")
        st.stop()

    st.markdown("### KPIs (Casa vs Fora)")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"#### {home_team} (Casa)")
        render_kpis(home)
    with c2:
        st.markdown(f"#### {away_team} (Fora)")
        render_kpis(away)


    st.markdown("### Perfil táctico (radar) — Casa vs Fora")
    r1, r2 = st.columns(2)
    with r1:
        scores = quadrant_scores(resumo[resumo["scope"] == "Casa"], home)
        fig = plot_radar(scores, title=f"{home_team} • Casa")
        st.pyplot(fig, clear_figure=True)
    with r2:
        scores = quadrant_scores(resumo[resumo["scope"] == "Fora"], away)
        fig = plot_radar(scores, title=f"{away_team} • Fora")
        st.pyplot(fig, clear_figure=True)

    st.markdown("### Ângulos a explorar (heurísticas)")
    ins = matchup_insights(home, away)
    if not ins:
        st.info("Não surgiram ângulos fortes com estas regras simples. Experimenta outro jogo ou consulta a aba Mercados para padrões específicos.")
    else:
        for s in ins:
            st.write("• " + s)

    st.markdown("### Check rápido (EG/Poisson) para evitar contradições")
    try:
        eg_h, eg_a, _dbg2 = expected_goals(resumo, serie, home_team, away_team, weight_recent=0.35, recent_n=5)
        if not (np.isnan(eg_h) or np.isnan(eg_a)):
            pb = poisson_probs(eg_h, eg_a, max_goals=10)
            c1, c2, c3 = st.columns(3)
            c1.metric("EG total", f"{(pb['EG Casa'] + pb['EG Fora']):.2f}")
            c2.metric("P(Over 2.5)", fmt_pct(pb["Over 2.5"]))
            c3.metric("P(BTTS)", fmt_pct(pb["BTTS Sim"]))
            if any("Over 2.5" in x for x in ins) and pb["Over 2.5"] < 0.35:
                st.warning("A heurística aponta para Over 2.5 (frequência histórica), mas o modelo de golos indica probabilidade baixa. Confirma na tab Pré-jogo e vê os detalhes do EG.")
    except Exception:
        pass

    st.divider()
    st.markdown("### Mercados mais característicos (Casa vs Fora)")
    m_home = mercados[(mercados["team"] == home_team) & (mercados["scope"] == "Casa") & (mercados["jogos"] >= min_games)].copy()
    m_away = mercados[(mercados["team"] == away_team) & (mercados["scope"] == "Fora") & (mercados["jogos"] >= min_games)].copy()

    # juntar por market para ver edges lado-a-lado
    join = m_home.merge(m_away, on="market", suffixes=("_casa", "_fora"))
    join = join[["market", "edge_vs_liga_casa", "edge_vs_liga_fora", "hit_rate_casa", "hit_rate_fora", "roi_unid_por_aposta_casa", "roi_unid_por_aposta_fora"]].copy()
    join["score_edge"] = join[["edge_vs_liga_casa", "edge_vs_liga_fora"]].mean(axis=1)

    top = join.dropna(subset=["score_edge"]).sort_values("score_edge", ascending=False).head(12)
    bot = join.dropna(subset=["score_edge"]).sort_values("score_edge", ascending=True).head(12)

    st.markdown("**Top (média de edge positiva nos dois lados)**")
    st.dataframe(format_mercados_table(top.drop(columns=["score_edge"])), hide_index=True, use_container_width=True)

    st.markdown("**Bottom (média de edge negativa nos dois lados)**")
    st.dataframe(format_mercados_table(bot.drop(columns=["score_edge"])), hide_index=True, use_container_width=True)

    download_button(join, f"{home_team}_casa_vs_{away_team}_fora_mercados.csv", "Descarregar comparação de mercados em CSV")

    # 🎯 Trading Lay (degradação graciosa)
    if lay_cand is not None and not lay_cand.empty:
        with st.expander("🎯 Cenários lay para este jogo", expanded=False):
            topn_lay = st.slider("Top N cenários (Lay)", 3, 15, 8, 1, key="con_lay_topn")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**{home_team} (Casa)**")
                d1 = lay_candidates_for_team(lay_cand, home_team, "Casa", top_n=topn_lay)
                render_lay_pills(d1, max_pills=min(6, topn_lay))
                _v, _sty = lay_table_view(d1)
                st.dataframe(_sty, hide_index=True, use_container_width=True)
            with c2:
                st.markdown(f"**{away_team} (Fora)**")
                d2 = lay_candidates_for_team(lay_cand, away_team, "Fora", top_n=topn_lay)
                render_lay_pills(d2, max_pills=min(6, topn_lay))
                _v, _sty = lay_table_view(d2)
                st.dataframe(_sty, hide_index=True, use_container_width=True)
            conv = lay_convergent_table(d1, d2, top_n=topn_lay)
            st.markdown("**Convergentes (Top N de ambos)**")
            if conv is None or conv.empty:
                st.caption("—")
            else:
                st.dataframe(conv, hide_index=True, use_container_width=True)

    st.divider()
    st.markdown("### Histórico directo (H2H)")
    h2h = serie[(serie["team"] == home_team) & (serie["opponent"] == away_team)].sort_values("date").copy()
    if h2h.empty:
        st.info("Sem jogos H2H no histórico (ou a Série Temporal não tem registos suficientes para este par).")
    else:
        h2h["outcome"] = np.where(h2h["gf"] > h2h["ga"], "V", np.where(h2h["gf"] == h2h["ga"], "E", "D"))
        n = len(h2h)
        v = int((h2h["outcome"] == "V").sum())
        e = int((h2h["outcome"] == "E").sum())
        d = int((h2h["outcome"] == "D").sum())
        g_total = (h2h["gf"] + h2h["ga"]).astype(float)
        btts = float(((h2h["gf"] > 0) & (h2h["ga"] > 0)).mean())
        over25 = float((g_total > 2.5).mean())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Jogos", f"{n}")
        c2.metric("Registo (do ponto de vista da casa seleccionada)", f"{v}V {e}E {d}D")
        c3.metric("Média golos", f"{g_total.mean():.2f}")
        c4.metric("BTTS / Over 2.5", f"{btts*100:.0f}% / {over25*100:.0f}%")
        st.caption(f"{home_team} marca em {((h2h['gf']>0).mean()*100):.0f}% dos H2H; {away_team} marca em {((h2h['ga']>0).mean()*100):.0f}% (n={n}).")

        try:
            eg_h2h, eg_a2h, _ = expected_goals(resumo, serie, home_team, away_team, weight_recent=0.35, recent_n=5)
            if not (np.isnan(eg_h2h) or np.isnan(eg_a2h)):
                pb_h2h = poisson_probs(eg_h2h, eg_a2h, max_goals=10)
                diff_btts = abs(float(btts) - float(pb_h2h.get("BTTS Sim", np.nan)))
                diff_o25 = abs(float(over25) - float(pb_h2h.get("Over 2.5", np.nan)))
                if np.isfinite(diff_btts) and diff_btts >= 0.15:
                    st.warning(
                        f"Divergência H2H vs modelo em BTTS: H2H {btts*100:.0f}% vs Poisson {pb_h2h['BTTS Sim']*100:.0f}%.",
                        icon="⚠️",
                    )
                if np.isfinite(diff_o25) and diff_o25 >= 0.15:
                    st.warning(
                        f"Divergência H2H vs modelo em Over 2.5: H2H {over25*100:.0f}% vs Poisson {pb_h2h['Over 2.5']*100:.0f}%.",
                        icon="⚠️",
                    )
        except Exception:
            pass

        st.markdown("#### Últimos H2H")
        last = h2h.sort_values("date", ascending=False).head(10)[["date", "venue", "gf", "ga", "outcome"]].copy()
        last["date"] = last["date"].dt.date.astype(str)
        last["resultado"] = last.apply(lambda r: f"{home_team} {int(r['gf'])}-{int(r['ga'])} {away_team}", axis=1)
        st.dataframe(last[["date", "venue", "resultado", "outcome"]], hide_index=True, use_container_width=True)

    st.caption("⚠️ Isto é análise estatística descritiva. Usa sempre contexto (lesões, calendário, matchups tácticos) e gestão de banca.")