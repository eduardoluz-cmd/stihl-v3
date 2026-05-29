"""
Análise de Confiabilidade de Ativos — Stihl
Protótipo desenvolvido pela Vent para validação com o cliente.

Replica o fluxo do relatório LCC-ZFM (Mar/2026) em ambiente interativo:
- KPIs globais (MTBF, MTTR, β, Custos)
- Análise temporal (MTBF/MTTR anuais com IQR e tendência)
- Weibull 2P + Curva da Banheira (Hazard)
- Custos corretivos e quebra por classe de custo (KOB1)
- Detalhamento por ordem

Para rodar: streamlit run app.py
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st
from scipy import stats
from datetime import datetime

import lcc as lcc_mod
from lcc import (
    farol_v2,
    classificar_beta_v2,
    classificar_tendencia,
    calcular_lcc,
    FAROL_EMOJI,
    FAROL_LABEL,
    HORIZONTE_ANOS,
)

# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="Stihl · Análise de Confiabilidade",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# DETECÇÃO DE TEMA (claro / escuro) — usa o tema ativo do Streamlit
# =============================================================================
def _detectar_tema() -> str:
    try:
        tipo = st.context.theme.type
        if tipo in ("light", "dark"):
            return tipo
    except Exception:
        pass
    return "light"


TEMA = _detectar_tema()
IS_DARK = TEMA == "dark"

# Cores Stihl + Vent (mantidas em ambos os temas)
STIHL_ORANGE = "#FF6600"
STIHL_ORANGE_LIGHT = "#FF8533"
GREEN_OK = "#22C55E"
YELLOW_WARN = "#EAB308"
RED_ALERT = "#EF4444"

# Paletas dependentes do tema
if IS_DARK:
    BG_DARK = "#0F1419"
    BG_CARD = "#1A2027"
    TEXT_PRIMARY = "#E8EAED"
    TEXT_MUTED = "#9AA0A6"
    GRID_COLOR = "#2A3038"
    VENT_TEAL = "#5EEAD4"
    SELECT_BG = BG_DARK
    IQR_FILL_ORANGE = "rgba(255, 102, 0, 0.15)"
    IQR_FILL_TEAL = "rgba(94, 234, 212, 0.15)"
    VIOLIN_FILL = "rgba(255, 102, 0, 0.3)"
else:
    BG_DARK = "#FFFFFF"
    BG_CARD = "#F8F9FA"
    TEXT_PRIMARY = "#1F2937"
    TEXT_MUTED = "#6B7280"
    GRID_COLOR = "#E5E7EB"
    VENT_TEAL = "#0D9488"
    SELECT_BG = "#FFFFFF"
    IQR_FILL_ORANGE = "rgba(255, 102, 0, 0.18)"
    IQR_FILL_TEAL = "rgba(13, 148, 136, 0.18)"
    VIOLIN_FILL = "rgba(255, 102, 0, 0.25)"

CARD_SHADOW = (
    "0 1px 3px rgba(0,0,0,0.4)" if IS_DARK else "0 1px 3px rgba(0,0,0,0.08)"
)

# CSS customizado (adapta-se ao tema ativo)
st.markdown(
    f"""
    <style>
        .stApp {{
            background: {BG_DARK};
        }}
        [data-testid="stSidebar"] {{
            background: {BG_CARD};
            border-right: 1px solid {GRID_COLOR};
        }}
        h1, h2, h3, h4 {{
            color: {TEXT_PRIMARY} !important;
            font-family: 'Helvetica Neue', sans-serif;
        }}
        h1 {{
            border-bottom: 3px solid {STIHL_ORANGE};
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .stTabs [data-baseweb="tab-list"] {{
            gap: 8px;
            background: transparent;
        }}
        .stTabs [data-baseweb="tab"] {{
            background: {BG_CARD};
            border-radius: 6px 6px 0 0;
            padding: 10px 20px;
            color: {TEXT_MUTED};
        }}
        .stTabs [aria-selected="true"] {{
            background: {STIHL_ORANGE} !important;
            color: white !important;
        }}
        .kpi-card {{
            background: {BG_CARD};
            border-left: 4px solid {STIHL_ORANGE};
            padding: 18px 22px;
            border-radius: 8px;
            height: 100%;
            box-shadow: {CARD_SHADOW};
        }}
        .kpi-label {{
            color: {TEXT_MUTED};
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }}
        .kpi-value {{
            color: {TEXT_PRIMARY};
            font-size: 28px;
            font-weight: 700;
            line-height: 1;
        }}
        .kpi-unit {{
            color: {TEXT_MUTED};
            font-size: 14px;
            margin-left: 4px;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge-red {{ background: {RED_ALERT}; color: white; }}
        .badge-yellow {{ background: {YELLOW_WARN}; color: black; }}
        .badge-green {{ background: {GREEN_OK}; color: white; }}
        .header-brand {{
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 4px;
        }}
        .brand-stihl {{
            background: {STIHL_ORANGE};
            color: white;
            padding: 4px 12px;
            font-weight: 900;
            font-style: italic;
            letter-spacing: 1px;
            border-radius: 2px;
        }}
        .brand-vent {{
            color: {VENT_TEAL};
            font-weight: 700;
            letter-spacing: 0.5px;
        }}
        .subtle {{ color: {TEXT_MUTED}; font-size: 13px; }}
        section[data-testid="stSidebar"] h2 {{
            font-size: 14px !important;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: {STIHL_ORANGE} !important;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# GERAÇÃO DE DADOS MOCK (replicando o relatório LCC-ZFM Mar/2026)
# =============================================================================
EQUIPAMENTOS = {
    "INJ001": {
        "denominacao": "INJ001-INJETORA DE MAGNÉSIO",
        "loc_instalacao": "BR01-MOT-FMG-INJEC1-INJ001",
        "centro_custo": "MOT-FMG",
        "alpha": 139004.562,
        "beta": 2.182,
        "n_falhas": 4545,
        "mtbf_global": 49.37,
        "mtbf_mediana": 20,
        "mttr_global": 2.98,
        "mttr_mediana": 2,
        "pico_custo": 176118.65,
        "ano_pico": 2023,
        "custo_medio": 73188.06,
        "tendencia_mtbf": -1.09,
        "tendencia_mttr": 0.01,
        "obs": "Crescimento progressivo",
        "obsolescencia": "Não há",
        "tend_mtbf_label": "N/D",
        "tend_custo_label": "N/D",
    },
    "INJ002": {
        "denominacao": "INJ002-INJETORA DE MAGNÉSIO",
        "loc_instalacao": "BR01-MOT-FMG-INJEC1-INJ002",
        "centro_custo": "MOT-FMG",
        "alpha": 154008.287,
        "beta": 2.644,
        "n_falhas": 4893,
        "mtbf_global": 45.88,
        "mtbf_mediana": 18,
        "mttr_global": 3.00,
        "mttr_mediana": 2,
        "pico_custo": 123644.97,
        "ano_pico": 2022,
        "custo_medio": 60322.81,
        "tendencia_mtbf": -2.62,
        "tendencia_mttr": 0.00,
        "obs": "Oscilação forte e alto custo recente",
        "obsolescencia": "Não há",
        "tend_mtbf_label": "N/D",
        "tend_custo_label": "N/D",
    },
    "INJ003": {
        "denominacao": "INJ003-INJETORA DE MAGNÉSIO",
        "loc_instalacao": "BR01-MOT-FMG-INJEC2-INJ003",
        "centro_custo": "MOT-FMG",
        "alpha": 142814.303,
        "beta": 2.018,
        "n_falhas": 3550,
        "mtbf_global": 63.03,
        "mtbf_mediana": 22,
        "mttr_global": 2.80,
        "mttr_mediana": 2,
        "pico_custo": 204537.69,
        "ano_pico": 2022,
        "custo_medio": 75096.57,
        "tendencia_mtbf": -1.22,
        "tendencia_mttr": -0.00,
        "obs": "Maior pico entre todas as máquinas",
        "obsolescencia": "Não há",
        "tend_mtbf_label": "N/D",
        "tend_custo_label": "N/D",
    },
    "INJ004": {
        "denominacao": "INJ004-INJETORA DE MAGNÉSIO",
        "loc_instalacao": "BR01-MOT-FMG-INJEC2-INJ004",
        "centro_custo": "MOT-FMG",
        "alpha": 141565.877,
        "beta": 2.193,
        "n_falhas": 3959,
        "mtbf_global": 56.63,
        "mtbf_mediana": 19,
        "mttr_global": 2.83,
        "mttr_mediana": 2,
        "pico_custo": 128334.39,
        "ano_pico": 2025,
        "custo_medio": 56957.08,
        "tendencia_mtbf": -2.13,
        "tendencia_mttr": 0.02,
        "obs": "Três anos seguidos de elevação",
        "obsolescencia": "Não há",
        "tend_mtbf_label": "N/D",
        "tend_custo_label": "N/D",
    },
}

CLASSES_CUSTO_DEPARA = {
    "48400100": "Serviço",
    "48400105": "Material",
    "42620510": "Material",
    "48800100": "Reforma",
    "42620501": "Material",
    "42620502": "Material",
    "42620504": "Material",
    "94301200": "Horas",
}

TIPOS_ORDEM = ["PM01", "PM02", "PM03", "PM04", "ZPM1", "ZPM2", "ZPM3"]


@st.cache_data
def gerar_dados_mock(seed: int = 42):
    """Gera dados sintéticos que reproduzem as características do relatório."""
    rng = np.random.default_rng(seed)

    registros_falhas = []
    registros_custos = []

    for tag, p in EQUIPAMENTOS.items():
        # Tempos entre falhas seguindo lognormal calibrada para os parâmetros do relatório.
        # Para lognormal(mu, sigma): mediana = exp(mu), média = exp(mu + sigma²/2)
        mu = np.log(p["mtbf_mediana"])
        sigma = np.sqrt(2 * np.log(p["mtbf_global"] / p["mtbf_mediana"]))
        mtbfs = rng.lognormal(mu, sigma, p["n_falhas"])
        mtbfs = np.clip(mtbfs, 1, None)

        # Tempos de reparo (mediana 2h, média ~2.8-3.0h)
        mu_r = np.log(p["mttr_mediana"])
        sigma_r = np.sqrt(2 * np.log(p["mttr_global"] / p["mttr_mediana"]))
        mttrs = rng.lognormal(mu_r, sigma_r, p["n_falhas"])
        mttrs = np.clip(mttrs, 0.1, None)

        # Distribuir falhas entre 2000 e 2025
        anos = rng.integers(2000, 2026, p["n_falhas"])

        # Custos (mais altos nos anos recentes para refletir o envelhecimento)
        peso_ano = (anos - 1999) / 26
        custos_base = rng.lognormal(7.5, 1.2, p["n_falhas"]) * (0.5 + 1.5 * peso_ano)

        for i in range(p["n_falhas"]):
            ordem = 10000000 + rng.integers(0, 9999999)
            nota = 20000000 + rng.integers(0, 9999999)
            tipo_ordem = rng.choice(TIPOS_ORDEM, p=[0.55, 0.08, 0.05, 0.05, 0.15, 0.07, 0.05])
            mes = rng.integers(1, 13)
            dia = rng.integers(1, 28)
            data = pd.Timestamp(year=int(anos[i]), month=int(mes), day=int(dia))

            registros_falhas.append({
                "Equipamento": tag,
                "Denominacao": p["denominacao"],
                "Loc_instalacao": p["loc_instalacao"],
                "Centro_custo": p["centro_custo"],
                "Ordem": ordem,
                "Nota": nota,
                "Tipo_ordem": tipo_ordem,
                "Status_nota": "SOLA" if rng.random() < 0.85 else "ABER",
                "Data": data,
                "Ano": int(anos[i]),
                "MTBF_h": round(float(mtbfs[i]), 2),
                "MTTR_h": round(float(mttrs[i]), 2),
                "Custo_total_reais": round(float(custos_base[i]), 2),
            })

            # Gerar 1-3 lançamentos KOB1 por ordem
            n_lanc = rng.integers(1, 4)
            for _ in range(n_lanc):
                classe = rng.choice(list(CLASSES_CUSTO_DEPARA.keys()))
                qtd = round(float(rng.uniform(0.5, 10)), 2)
                valor = round(float(custos_base[i] / n_lanc * rng.uniform(0.7, 1.3)), 2)
                registros_custos.append({
                    "Equipamento": tag,
                    "Ordem": ordem,
                    "Data_lancamento": data,
                    "Ano": int(anos[i]),
                    "Classe_custo": classe,
                    "Categoria": CLASSES_CUSTO_DEPARA[classe],
                    "Qtd_total": qtd,
                    "Valor_MR": valor,
                    "Tipo_ordem": tipo_ordem,
                })

    df_falhas = pd.DataFrame(registros_falhas)
    df_custos = pd.DataFrame(registros_custos)
    return df_falhas, df_custos


def fit_weibull_2p(times: np.ndarray):
    """Ajusta Weibull 2P por máxima verossimilhança via scipy."""
    times = np.asarray(times, dtype=float)
    times = times[times > 0]
    if len(times) < 5:
        return None, None
    shape, loc, scale = stats.weibull_min.fit(times, floc=0)
    return scale, shape  # alpha, beta


def calcular_kpis(df: pd.DataFrame):
    """Calcula KPIs agregados sobre o DF filtrado."""
    if df.empty:
        return {"mtbf": 0, "mttr": 0, "beta": 0, "custo_total": 0, "n_notas": 0}

    mtbf = df["MTBF_h"].mean()
    mttr = df["MTTR_h"].mean()
    custo_total = df["Custo_total_reais"].sum()
    n_notas = len(df)

    # Beta agregado (Weibull fit nos tempos de operação acumulados)
    if len(df) >= 30:
        cumulative = df.sort_values("Data")["MTBF_h"].cumsum().values
        _, beta = fit_weibull_2p(cumulative)
    else:
        beta = np.nan

    return {
        "mtbf": mtbf,
        "mttr": mttr,
        "beta": beta if beta is not None else 0,
        "custo_total": custo_total,
        "n_notas": n_notas,
    }


_BADGE_CLS = {"verde": "badge-green", "amarelo": "badge-yellow", "vermelho": "badge-red"}


def classificar_beta(beta: float) -> tuple[str, str]:
    """Retorna (texto, classe CSS) para o badge de fase de vida (régua v2)."""
    fase, cor = classificar_beta_v2(beta)
    return fase, _BADGE_CLS[cor]


def farol_equipamento(eq: dict) -> str:
    """Aplica farol v2 para uma injetora (com tendências computadas do mock)."""
    return farol_v2(
        beta=eq["beta"],
        obsolescencia=eq.get("obsolescencia", "Não há"),
        tend_mtbf=eq.get("tend_mtbf_label", "N/D"),
        tend_custo=eq.get("tend_custo_label", "N/D"),
    )["cor"]


def recomendacao_equipamento(stats_eq: dict) -> tuple[str, str]:
    """Recomendação derivada do farol v2: Manter / Acompanhar / Substituir."""
    cor = farol_equipamento(stats_eq)
    return FAROL_LABEL[cor], _BADGE_CLS[cor]


@st.cache_data
def carregar_excel_dados() -> pd.DataFrame:
    """Carrega aba Dados + MATRIZ do workbook (cacheado pelo Streamlit)."""
    return lcc_mod.carregar_dados_excel()


def calcular_tendencias_injetora(df_falhas_eq: pd.DataFrame,
                                 df_custos_eq: pd.DataFrame) -> tuple[str, str]:
    """Calcula rótulos de tendência (MTBF, custo) para uma injetora."""
    mtbf_anual = df_falhas_eq.groupby("Ano")["MTBF_h"].median()
    tend_mtbf = classificar_tendencia(mtbf_anual, tipo="mtbf")
    custo_anual = df_custos_eq.groupby("Ano")["Valor_MR"].sum()
    tend_custo = classificar_tendencia(custo_anual, tipo="custo")
    return tend_mtbf, tend_custo


# =============================================================================
# LAYOUT — HEADER
# =============================================================================
df_falhas_all, df_custos_all = gerar_dados_mock()

# Compute trend labels (Queda/Estável/Alta + Crescente/Estável/Decrescente) once
# per injetora — feeds farol v2 e agregações.
for _tag, _eq in EQUIPAMENTOS.items():
    _df_eq = df_falhas_all[df_falhas_all["Equipamento"] == _tag]
    _df_custo_eq = df_custos_all[df_custos_all["Equipamento"] == _tag]
    _tm, _tc = calcular_tendencias_injetora(_df_eq, _df_custo_eq)
    _eq["tend_mtbf_label"] = _tm
    _eq["tend_custo_label"] = _tc

# Carrega base de 742 ativos do Excel (aba Dados + MATRIZ)
df_excel = carregar_excel_dados()

st.markdown(
    f"""
    <div class="header-brand">
        <span class="brand-stihl">STIHL</span>
        <span style="color: {TEXT_MUTED}; font-size: 14px;">×</span>
        <span class="brand-vent">vent'</span>
    </div>
    """,
    unsafe_allow_html=True,
)
st.title("Análise de Confiabilidade de Ativos")
st.markdown(
    f'<p class="subtle">Dashboard de cálculo de vida útil — Injetoras de Magnésio · '
    f"Dados consolidados das transações SAP IW28, IW38, IW47 e KOB1</p>",
    unsafe_allow_html=True,
)

# =============================================================================
# SIDEBAR — FILTROS
# =============================================================================
with st.sidebar:
    st.markdown(
        f'<div style="text-align:center; padding: 10px 0 20px 0;">'
        f'<span class="brand-stihl">STIHL</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.header("Filtros")

    equipamentos_sel = st.multiselect(
        "Equipamento (TAG)",
        options=list(EQUIPAMENTOS.keys()),
        default=list(EQUIPAMENTOS.keys()),
    )

    anos_min, anos_max = int(df_falhas_all["Ano"].min()), int(df_falhas_all["Ano"].max())
    periodo = st.slider(
        "Período",
        min_value=anos_min,
        max_value=anos_max,
        value=(anos_min, anos_max),
    )

    tipos_sel = st.multiselect(
        "Tipo de Ordem",
        options=TIPOS_ORDEM,
        default=["PM01", "ZPM1"],
        help="PM01/ZPM1 = corretivas (padrão do relatório LCC-ZFM)",
    )

    status_sel = st.multiselect(
        "Status da Nota",
        options=["SOLA", "ABER"],
        default=["SOLA"],
    )

    st.markdown("---")
    st.markdown(
        f'<p class="subtle">⚙️ <b>Pipeline ETL:</b> última carga em '
        f'{datetime.now().strftime("%d/%m/%Y %H:%M")}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p class="subtle">📊 Fonte: IW28 / IW38 / IW47 / KOB1</p>',
        unsafe_allow_html=True,
    )

# Aplicar filtros
mask = (
    df_falhas_all["Equipamento"].isin(equipamentos_sel)
    & df_falhas_all["Ano"].between(periodo[0], periodo[1])
    & df_falhas_all["Tipo_ordem"].isin(tipos_sel)
    & df_falhas_all["Status_nota"].isin(status_sel)
)
df = df_falhas_all[mask].copy()
df_custos = df_custos_all[
    df_custos_all["Equipamento"].isin(equipamentos_sel)
    & df_custos_all["Ano"].between(periodo[0], periodo[1])
    & df_custos_all["Tipo_ordem"].isin(tipos_sel)
].copy()

if df.empty:
    st.warning("⚠️ Nenhum dado para os filtros selecionados.")
    st.stop()

# =============================================================================
# KPIs GLOBAIS
# =============================================================================
kpis = calcular_kpis(df)
fase_txt, fase_cls = classificar_beta(kpis["beta"])

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-label">MTBF Global</div>'
        f'<div class="kpi-value">{kpis["mtbf"]:.1f}<span class="kpi-unit">h</span></div>'
        f"</div>",
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-label">MTTR Global</div>'
        f'<div class="kpi-value">{kpis["mttr"]:.2f}<span class="kpi-unit">h</span></div>'
        f"</div>",
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-label">β (Weibull)</div>'
        f'<div class="kpi-value">{kpis["beta"]:.2f}</div>'
        f'<span class="badge {fase_cls}" style="margin-top:6px; display:inline-block;">{fase_txt}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
with c4:
    st.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-label">Custo Corretivo</div>'
        f'<div class="kpi-value">R$ {kpis["custo_total"]/1000:.0f}<span class="kpi-unit">k</span></div>'
        f"</div>",
        unsafe_allow_html=True,
    )
with c5:
    st.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-label">Nº Notas</div>'
        f'<div class="kpi-value">{kpis["n_notas"]:,}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# =============================================================================
# ABAS
# =============================================================================
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
    [
        "📊 Visão Geral",
        "⏱️ MTBF",
        "🔧 MTTR",
        "📈 Weibull & Hazard",
        "💰 Custos",
        "🔍 Detalhamento",
        "🚦 Farol & Priorização",
        "💵 ROI / LCC",
    ]
)

# --- Tema base do plotly ---
PLOTLY_LAYOUT = dict(
    paper_bgcolor=BG_DARK,
    plot_bgcolor=BG_DARK,
    font=dict(color=TEXT_PRIMARY, family="Helvetica Neue, sans-serif"),
    xaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR),
    yaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR),
    margin=dict(l=40, r=20, t=50, b=40),
    hoverlabel=dict(bgcolor=BG_CARD, font_color=TEXT_PRIMARY),
)


# =============================================================================
# ABA 1 — VISÃO GERAL
# =============================================================================
with tab1:
    st.subheader("Comparativo entre Equipamentos")
    st.markdown(
        f'<p class="subtle">Síntese dos indicadores de confiabilidade por equipamento. '
        f"Recomendação automática baseada em β, tendência de MTBF e pico de custo.</p>",
        unsafe_allow_html=True,
    )

    linhas = []
    for tag in equipamentos_sel:
        eq = EQUIPAMENTOS[tag]
        rec, rec_cls = recomendacao_equipamento(eq)
        fase, _ = classificar_beta(eq["beta"])
        linhas.append({
            "Farol": FAROL_EMOJI[farol_equipamento(eq)],
            "Equipamento": tag,
            "N": eq["n_falhas"],
            "MTBF mediana (h)": eq["mtbf_mediana"],
            "MTBF média (h)": eq["mtbf_global"],
            "MTTR mediana (h)": eq["mttr_mediana"],
            "β": eq["beta"],
            "Fase": fase,
            "Obsolescência": eq.get("obsolescencia", "Não há"),
            "Tend. MTBF": eq.get("tend_mtbf_label", "N/D"),
            "Tend. Custo": eq.get("tend_custo_label", "N/D"),
            "Pico Custo (R$)": eq["pico_custo"],
            "Ano Pico": eq["ano_pico"],
            "Recomendação": rec,
        })

    df_resumo = pd.DataFrame(linhas)
    st.dataframe(
        df_resumo,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Farol": st.column_config.TextColumn(
                "Farol",
                help="🟢 Manter · 🟡 Acompanhar · 🔴 Substituir",
                width="small",
            ),
            "Pico Custo (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "β": st.column_config.NumberColumn(format="%.2f"),
            "MTBF média (h)": st.column_config.NumberColumn(format="%.1f"),
        },
    )

    st.markdown("<br>", unsafe_allow_html=True)
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("β comparativo")
        fig = go.Figure()
        # Régua v2: <0.9 amarelo, 0.9-1.2 verde, 1.2-1.5 amarelo, >1.5 vermelho
        def _cor_beta(b):
            if b < 0.9 or (1.2 < b <= 1.5):
                return YELLOW_WARN
            if b > 1.5:
                return RED_ALERT
            return GREEN_OK
        cores_beta = [_cor_beta(EQUIPAMENTOS[t]["beta"]) for t in equipamentos_sel]
        fig.add_trace(go.Bar(
            x=equipamentos_sel,
            y=[EQUIPAMENTOS[t]["beta"] for t in equipamentos_sel],
            marker_color=cores_beta,
            text=[f"{EQUIPAMENTOS[t]['beta']:.2f}" for t in equipamentos_sel],
            textposition="outside",
            textfont=dict(color=TEXT_PRIMARY, size=14),
        ))
        fig.add_hline(y=1, line_dash="dash", line_color=TEXT_MUTED,
                      annotation_text="β=1 (aleatório)", annotation_position="right",
                      annotation_font_color=TEXT_MUTED)
        fig.update_layout(**PLOTLY_LAYOUT, height=350,
                          yaxis_title="β", showlegend=False,
                          title_text="Indicador β por equipamento")
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Pico de custo corretivo")
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=equipamentos_sel,
            y=[EQUIPAMENTOS[t]["pico_custo"] for t in equipamentos_sel],
            marker_color=STIHL_ORANGE,
            text=[f"R$ {EQUIPAMENTOS[t]['pico_custo']/1000:.1f}k" for t in equipamentos_sel],
            textposition="outside",
            textfont=dict(color=TEXT_PRIMARY, size=12),
            customdata=[EQUIPAMENTOS[t]["ano_pico"] for t in equipamentos_sel],
            hovertemplate="<b>%{x}</b><br>Pico: R$ %{y:,.2f}<br>Ano: %{customdata}<extra></extra>",
        ))
        fig.update_layout(**PLOTLY_LAYOUT, height=350,
                          yaxis_title="R$", showlegend=False,
                          title_text="Maior custo corretivo histórico")
        st.plotly_chart(fig, use_container_width=True)

    st.info(
        "📌 **Leitura técnica:** Todas as injetoras apresentam β > 1 → fase de desgaste. "
        "INJ002 lidera o indicador β (2,64) — principal candidato à substituição/reforma. "
        "INJ003 registra o maior pico histórico de custo (R$ 204k em 2022)."
    )


# =============================================================================
# ABA 2 — MTBF
# =============================================================================
with tab2:
    st.subheader("MTBF Anual — Mediana, IQR e Tendência")

    col_focus_mtbf, col_tipo_mtbf = st.columns([2, 1])
    with col_focus_mtbf:
        eq_focus = st.selectbox(
            "Equipamento para análise detalhada",
            options=equipamentos_sel,
            key="mtbf_focus",
        )
    with col_tipo_mtbf:
        tipo_grafico_mtbf = st.radio(
            "Tipo de gráfico",
            options=["Linha + IQR", "Barras"],
            horizontal=True,
            key="mtbf_chart_type",
        )

    df_eq = df[df["Equipamento"] == eq_focus]

    agg = df_eq.groupby("Ano")["MTBF_h"].agg(
        mediana="median",
        p25=lambda x: np.percentile(x, 25),
        p75=lambda x: np.percentile(x, 75),
        n="count",
    ).reset_index()

    fig = go.Figure()
    if tipo_grafico_mtbf == "Linha + IQR":
        fig.add_trace(go.Scatter(
            x=list(agg["Ano"]) + list(agg["Ano"])[::-1],
            y=list(agg["p75"]) + list(agg["p25"])[::-1],
            fill="toself",
            fillcolor=IQR_FILL_ORANGE,
            line=dict(color="rgba(0,0,0,0)"),
            name="IQR (P25–P75)",
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=agg["Ano"], y=agg["mediana"],
            mode="lines+markers+text",
            line=dict(color=STIHL_ORANGE, width=3),
            marker=dict(size=8, color=STIHL_ORANGE),
            text=agg["n"],
            textposition="top center",
            textfont=dict(size=10, color=TEXT_MUTED),
            name="Mediana (texto=N falhas)",
        ))
    else:
        fig.add_trace(go.Bar(
            x=agg["Ano"], y=agg["mediana"],
            marker_color=STIHL_ORANGE,
            text=[f"{v:.1f}" for v in agg["mediana"]],
            textposition="outside",
            textfont=dict(color=TEXT_PRIMARY, size=11),
            error_y=dict(
                type="data", symmetric=False,
                array=(agg["p75"] - agg["mediana"]).clip(lower=0),
                arrayminus=(agg["mediana"] - agg["p25"]).clip(lower=0),
                color=TEXT_MUTED, thickness=1.5, width=6,
            ),
            customdata=agg["n"],
            hovertemplate="<b>%{x}</b><br>Mediana: %{y:.1f} h<br>N falhas: %{customdata}<extra></extra>",
            name="Mediana (barras com IQR)",
        ))

    if len(agg) >= 2:
        z = np.polyfit(agg["Ano"], agg["mediana"], 1)
        p = np.poly1d(z)
        fig.add_trace(go.Scatter(
            x=agg["Ano"], y=p(agg["Ano"]),
            mode="lines",
            line=dict(color=VENT_TEAL, dash="dash", width=2),
            name=f"Tendência ({z[0]:+.2f} h/ano)",
        ))

    fig.update_layout(
        **PLOTLY_LAYOUT, height=480,
        title_text=f"MTBF anual — {eq_focus}",
        xaxis_title="Ano", yaxis_title="MTBF (Horas)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.subheader("Distribuição de MTBF (escala log)")
        fig = go.Figure()
        for tag in equipamentos_sel:
            dados = df[df["Equipamento"] == tag]["MTBF_h"]
            fig.add_trace(go.Violin(
                y=dados,
                name=tag,
                line_color=STIHL_ORANGE,
                line_width=1.2,
                fillcolor="rgba(255, 102, 0, 0.75)",
                opacity=0.95,
                box_visible=False,
                meanline_visible=True,
                meanline=dict(color=TEXT_PRIMARY, width=1.5),
                points=False,
                spanmode="hard",
                scalemode="count",
                scalegroup="injetoras_mtbf",
                width=0.9,
                hovertemplate="<b>%{x}</b><br>MTBF: %{y:.1f} h<extra></extra>",
            ))
        fig.update_yaxes(type="log")
        fig.update_layout(
            **PLOTLY_LAYOUT, height=420,
            title_text="Distribuição de MTBF por máquina (escala log)",
            xaxis_title="TAG",
            yaxis_title="MTBF (Horas) [log]",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Estatísticas MTBF")
        tbl = df.groupby("Equipamento")["MTBF_h"].agg(
            N="count", Media="mean", Mediana="median",
            Min="min", Max="max",
        ).reset_index()
        tbl.insert(
            0, "Farol",
            tbl["Equipamento"].map(
                lambda t: FAROL_EMOJI[farol_equipamento(EQUIPAMENTOS[t])]
            ),
        )
        tbl["Media"] = tbl["Media"].round(2)
        tbl["Mediana"] = tbl["Mediana"].round(1)
        tbl["Min"] = tbl["Min"].round(1)
        tbl["Max"] = tbl["Max"].round(1)
        st.dataframe(
            tbl, hide_index=True, use_container_width=True,
            column_config={
                "Farol": st.column_config.TextColumn(
                    "Farol",
                    help="🟢 Manter · 🟡 Acompanhar · 🔴 Substituir",
                    width="small",
                ),
            },
        )
        st.caption(
            "💡 Em distribuições com cauda longa (média >> mediana), a mediana "
            "e o IQR são indicadores mais robustos para comparações e metas."
        )


# =============================================================================
# ABA 3 — MTTR
# =============================================================================
with tab3:
    st.subheader("MTTR Anual — Mediana, Média, IQR e Tendência")

    col_focus_mttr, col_tipo_mttr = st.columns([2, 1])
    with col_focus_mttr:
        eq_focus_mttr = st.selectbox(
            "Equipamento para análise detalhada",
            options=equipamentos_sel,
            key="mttr_focus",
        )
    with col_tipo_mttr:
        tipo_grafico_mttr = st.radio(
            "Tipo de gráfico",
            options=["Linha + IQR", "Barras"],
            horizontal=True,
            key="mttr_chart_type",
        )

    df_eq = df[df["Equipamento"] == eq_focus_mttr]

    agg = df_eq.groupby("Ano")["MTTR_h"].agg(
        mediana="median",
        media="mean",
        p25=lambda x: np.percentile(x, 25),
        p75=lambda x: np.percentile(x, 75),
        n="count",
    ).reset_index()

    fig = go.Figure()
    if tipo_grafico_mttr == "Linha + IQR":
        fig.add_trace(go.Scatter(
            x=list(agg["Ano"]) + list(agg["Ano"])[::-1],
            y=list(agg["p75"]) + list(agg["p25"])[::-1],
            fill="toself",
            fillcolor=IQR_FILL_TEAL,
            line=dict(color="rgba(0,0,0,0)"),
            name="IQR (P25–P75)",
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=agg["Ano"], y=agg["mediana"],
            mode="lines+markers", line=dict(color=GREEN_OK, width=3),
            marker=dict(size=8), name="Mediana",
        ))
        fig.add_trace(go.Scatter(
            x=agg["Ano"], y=agg["media"],
            mode="lines+markers", line=dict(color=STIHL_ORANGE, width=2),
            marker=dict(size=7, symbol="square"), name="Média",
        ))
    else:
        fig.add_trace(go.Bar(
            x=agg["Ano"], y=agg["mediana"],
            marker_color=GREEN_OK,
            name="Mediana",
            text=[f"{v:.1f}" for v in agg["mediana"]],
            textposition="outside",
            textfont=dict(color=TEXT_PRIMARY, size=10),
            error_y=dict(
                type="data", symmetric=False,
                array=(agg["p75"] - agg["mediana"]).clip(lower=0),
                arrayminus=(agg["mediana"] - agg["p25"]).clip(lower=0),
                color=TEXT_MUTED, thickness=1.5, width=6,
            ),
        ))
        fig.add_trace(go.Bar(
            x=agg["Ano"], y=agg["media"],
            marker_color=STIHL_ORANGE,
            name="Média",
            text=[f"{v:.1f}" for v in agg["media"]],
            textposition="outside",
            textfont=dict(color=TEXT_PRIMARY, size=10),
        ))

    if len(agg) >= 2:
        z = np.polyfit(agg["Ano"], agg["mediana"], 1)
        p = np.poly1d(z)
        fig.add_trace(go.Scatter(
            x=agg["Ano"], y=p(agg["Ano"]),
            mode="lines", line=dict(color=VENT_TEAL, dash="dash"),
            name=f"Tendência ({z[0]:+.3f} h/ano)",
        ))

    fig.update_layout(
        **PLOTLY_LAYOUT, height=480,
        title_text=f"MTTR anual — {eq_focus_mttr}",
        xaxis_title="Ano", yaxis_title="MTTR (Horas)",
        barmode="group" if tipo_grafico_mttr == "Barras" else None,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

    diff_pct = ((agg["media"] - agg["mediana"]) / agg["mediana"] * 100).mean()
    if diff_pct > 30:
        st.warning(
            f"⚠️ **Outliers detectados:** A média de MTTR está em torno de "
            f"{diff_pct:.0f}% acima da mediana — indica reparos excepcionalmente "
            f"longos (assimetria positiva). Investigar eventos extremos."
        )

    st.subheader("MTTR resumo por equipamento")
    tbl_mttr = df.groupby("Equipamento")["MTTR_h"].agg(
        N="count", Mediana="median", Media="mean",
    ).reset_index()
    tbl_mttr.insert(
        0, "Farol",
        tbl_mttr["Equipamento"].map(
            lambda t: FAROL_EMOJI[farol_equipamento(EQUIPAMENTOS[t])]
        ),
    )
    tbl_mttr["Mediana"] = tbl_mttr["Mediana"].round(1)
    tbl_mttr["Media"] = tbl_mttr["Media"].round(2)
    st.dataframe(
        tbl_mttr, hide_index=True, use_container_width=True,
        column_config={
            "Farol": st.column_config.TextColumn(
                "Farol",
                help="🟢 Manter · 🟡 Acompanhar · 🔴 Substituir",
                width="small",
            ),
        },
    )


# =============================================================================
# ABA 4 — WEIBULL & HAZARD
# =============================================================================
with tab4:
    st.subheader("Análise Weibull 2P + Curva da Banheira")
    st.markdown(
        f'<p class="subtle">Ajuste por máxima verossimilhança (MLE) sobre os tempos '
        f"acumulados até a falha. Curva da banheira mostra a taxa de falha instantânea ao longo do tempo.</p>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Gráfico de Probabilidade Weibull")
        eq_w = st.selectbox("Equipamento", options=equipamentos_sel, key="weibull_eq")
        p = EQUIPAMENTOS[eq_w]

        # Gera dados sintéticos do Weibull(alpha, beta) para o probability plot
        rng = np.random.default_rng(hash(eq_w) % 1000)
        samples = stats.weibull_min.rvs(p["beta"], scale=p["alpha"], size=500, random_state=rng)
        samples = np.sort(samples)
        ranks = (np.arange(1, len(samples) + 1) - 0.3) / (len(samples) + 0.4)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=samples, y=ranks * 100,
            mode="markers", marker=dict(color=STIHL_ORANGE, size=5),
            name=f"Falhas observadas",
        ))
        t_line = np.logspace(np.log10(samples.min()), np.log10(samples.max()), 100)
        cdf_line = stats.weibull_min.cdf(t_line, p["beta"], scale=p["alpha"])
        fig.add_trace(go.Scatter(
            x=t_line, y=cdf_line * 100,
            mode="lines", line=dict(color=VENT_TEAL, width=2),
            name=f"Weibull_2P (α={p['alpha']:.0f}, β={p['beta']:.2f})",
        ))
        fig.update_xaxes(type="log", title="Tempo (escala log)")
        fig.update_yaxes(title="Fração Acumulada de Falhas (%)")
        fig.update_layout(
            **PLOTLY_LAYOUT, height=420,
            title_text=f"Probabilidade Weibull — {eq_w}",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

        fase_eq, fase_cls_eq = classificar_beta(p["beta"])
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">Interpretação</div>'
            f'<div style="color:{TEXT_PRIMARY}; margin-top:8px;">'
            f"<b>β = {p['beta']:.2f}</b> → "
            f'<span class="badge {fase_cls_eq}">{fase_eq}</span><br>'
            f"<span class='subtle'>α (vida característica) = {p['alpha']:,.0f} h — "
            f"tempo em que 63,2% das falhas ocorrem.</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown("##### Curva da Banheira (Hazard Function)")
        fig = go.Figure()
        cores_hf = px.colors.sequential.Oranges_r[:len(equipamentos_sel)]
        for i, tag in enumerate(equipamentos_sel):
            p = EQUIPAMENTOS[tag]
            t = np.linspace(1000, 280000, 200)
            hf = (p["beta"] / p["alpha"]) * (t / p["alpha"]) ** (p["beta"] - 1)
            fig.add_trace(go.Scatter(
                x=t, y=hf,
                mode="lines", name=f"{tag} (β={p['beta']:.2f})",
                line=dict(width=2.5),
            ))
        fig.update_layout(
            **PLOTLY_LAYOUT, height=420,
            title_text="Taxa de falha instantânea — todos os equipamentos",
            xaxis_title="Tempo", yaxis_title="Taxa de falha instantânea",
            yaxis_tickformat=".2e",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.info(
            "📈 Quando todas as curvas são crescentes (β > 1), todos os equipamentos "
            "encontram-se na fase de desgaste — comportamento típico de fim de vida útil."
        )


# =============================================================================
# ABA 5 — CUSTOS
# =============================================================================
with tab5:
    st.subheader("Custo Corretivo Anual")

    df_custos_filt = df_custos[df_custos["Equipamento"].isin(equipamentos_sel)]
    custos_anuais = df_custos_filt.groupby(["Equipamento", "Ano"])["Valor_MR"].sum().reset_index()

    fig = go.Figure()
    cores_eq = {tag: px.colors.sequential.Oranges_r[i] for i, tag in enumerate(equipamentos_sel)}
    for tag in equipamentos_sel:
        d = custos_anuais[custos_anuais["Equipamento"] == tag].sort_values("Ano")
        fig.add_trace(go.Scatter(
            x=d["Ano"], y=d["Valor_MR"],
            mode="lines+markers", name=tag,
            line=dict(width=2.5),
            marker=dict(size=7),
        ))
    fig.update_layout(
        **PLOTLY_LAYOUT, height=420,
        xaxis_title="Ano", yaxis_title="Custo (R$)",
        title_text="Custo corretivo anual por equipamento",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Custo Acumulado")
    st.markdown(
        f'<p class="subtle">Soma corrida do custo corretivo ao longo do tempo — '
        f"útil para comparar o investimento total já consumido por equipamento.</p>",
        unsafe_allow_html=True,
    )

    custos_acum = custos_anuais.sort_values(["Equipamento", "Ano"]).copy()
    custos_acum["Acumulado"] = custos_acum.groupby("Equipamento")["Valor_MR"].cumsum()
    total_acumulado = custos_acum.groupby("Ano")["Valor_MR"].sum().sort_index().cumsum()

    fig_cum = go.Figure()
    for tag in equipamentos_sel:
        d = custos_acum[custos_acum["Equipamento"] == tag]
        fig_cum.add_trace(go.Scatter(
            x=d["Ano"], y=d["Acumulado"],
            mode="lines+markers", name=tag,
            line=dict(width=2.5),
            marker=dict(size=6),
            hovertemplate="<b>%{x}</b><br>Acumulado: R$ %{y:,.0f}<extra>" + tag + "</extra>",
        ))
    fig_cum.add_trace(go.Scatter(
        x=total_acumulado.index, y=total_acumulado.values,
        mode="lines", name="Total da frota",
        line=dict(color=VENT_TEAL, width=3, dash="dot"),
        hovertemplate="<b>%{x}</b><br>Total: R$ %{y:,.0f}<extra>Frota</extra>",
    ))
    fig_cum.update_layout(
        **PLOTLY_LAYOUT, height=420,
        xaxis_title="Ano", yaxis_title="Custo acumulado (R$)",
        title_text="Custo corretivo acumulado ao longo do período",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    if not total_acumulado.empty:
        st.caption(
            f"💵 Total acumulado da frota no período filtrado: "
            f"**R$ {total_acumulado.iloc[-1]:,.0f}** "
            f"({len(equipamentos_sel)} equipamento(s), "
            f"{int(total_acumulado.index.min())}–{int(total_acumulado.index.max())})."
        )

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Custo por Classe (KOB1)")
        custos_classe = df_custos_filt.groupby("Categoria")["Valor_MR"].sum().reset_index()
        custos_classe = custos_classe.sort_values("Valor_MR", ascending=True)
        fig = go.Figure(go.Bar(
            x=custos_classe["Valor_MR"], y=custos_classe["Categoria"],
            orientation="h",
            marker_color=STIHL_ORANGE,
            text=[f"R$ {v/1000:.0f}k" for v in custos_classe["Valor_MR"]],
            textposition="outside",
            textfont=dict(color=TEXT_PRIMARY),
        ))
        fig.update_layout(**PLOTLY_LAYOUT, height=380,
                          xaxis_title="R$", title_text="Quebra por categoria")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("DE-PARA aplicado: classes de custo R40 → P10 → categoria.")

    with col_b:
        st.subheader("Corretivo vs Preventivo")
        df_custos_filt["Manutencao"] = df_custos_filt["Tipo_ordem"].apply(
            lambda x: "Corretiva" if x in ["PM01", "ZPM1"] else "Preventiva"
        )
        manut = df_custos_filt.groupby("Manutencao")["Valor_MR"].sum().reset_index()
        fig = go.Figure(go.Pie(
            labels=manut["Manutencao"], values=manut["Valor_MR"],
            marker=dict(colors=[STIHL_ORANGE, VENT_TEAL]),
            textinfo="label+percent",
            textfont=dict(color=TEXT_PRIMARY, size=14),
            hole=0.5,
        ))
        fig.update_layout(**PLOTLY_LAYOUT, height=380,
                          title_text="Distribuição corretivo × preventivo")
        st.plotly_chart(fig, use_container_width=True)


# =============================================================================
# ABA 6 — DETALHAMENTO
# =============================================================================
with tab6:
    st.subheader("Detalhamento por Ordem")
    st.markdown(
        f'<p class="subtle">Join entre IW28 (notas) + IW38 (ordens) + IW47 (trabalho real) + KOB1 (custos). '
        f"Tabela completamente filtrável e exportável.</p>",
        unsafe_allow_html=True,
    )

    col_top1, col_top2, col_top3 = st.columns([1, 1, 2])
    with col_top1:
        ordenar_por = st.selectbox(
            "Ordenar por",
            ["Data", "Custo_total_reais", "MTBF_h", "MTTR_h"],
            index=1,
        )
    with col_top2:
        direcao = st.radio("Ordem", ["Desc", "Asc"], horizontal=True)

    df_tabela = df.sort_values(ordenar_por, ascending=(direcao == "Asc")).head(500)

    st.dataframe(
        df_tabela[[
            "Equipamento", "Ordem", "Nota", "Tipo_ordem", "Status_nota",
            "Data", "MTBF_h", "MTTR_h", "Custo_total_reais", "Loc_instalacao",
        ]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Custo_total_reais": st.column_config.NumberColumn(
                "Custo Total (R$)", format="R$ %.2f"
            ),
            "MTBF_h": st.column_config.NumberColumn("MTBF (h)", format="%.1f"),
            "MTTR_h": st.column_config.NumberColumn("MTTR (h)", format="%.2f"),
            "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
        },
    )

    st.caption(f"Exibindo top 500 de {len(df):,} registros filtrados.")

    st.download_button(
        "📥 Exportar dados filtrados (.csv)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"stihl_confiabilidade_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


# =============================================================================
# ABA 7 — FAROL & PRIORIZAÇÃO (base 742 ativos do Excel)
# =============================================================================
with tab7:
    st.subheader("Farol de Saúde dos Ativos — Régua de Decisão por Risco")
    st.markdown(
        f'<p class="subtle">Régua: base por β (faixas 0,9 / 1,2 / 1,5) + Obsolescência '
        f"(Total força crítico, Parcial agrava 1 nível) + Tendência MTBF/Custo (somente Queda e "
        f"Crescente agravam). O farol nunca melhora por tendência positiva. Base: "
        f"{len(df_excel)} ativos do workbook DASHBOARD_LCC.</p>",
        unsafe_allow_html=True,
    )

    # ---- Aplica farol v2 a todos os ativos ----
    @st.cache_data
    def _farol_excel(df_in: pd.DataFrame) -> pd.DataFrame:
        out = df_in.copy()
        cores, fases, agravs = [], [], []
        for _, r in out.iterrows():
            f = farol_v2(
                beta=r["Beta"],
                obsolescencia=r["Obsolescencia"],
                tend_mtbf="N/D",
                tend_custo="N/D",
            )
            cores.append(f["cor"])
            fases.append(f["fase_beta"])
            agravs.append(", ".join(f["agravantes"]) if f["agravantes"] else "—")
        out["Farol_cor"] = cores
        out["Fase β"] = fases
        out["Agravantes"] = agravs
        out["Farol"] = out["Farol_cor"].map(FAROL_EMOJI)
        out["Recomendação"] = out["Farol_cor"].map(FAROL_LABEL)
        return out

    df_far = _farol_excel(df_excel)
    df_far["Mini_fab"] = df_far["Mini_fab"].fillna("(sem)").astype(str).replace(
        {"nan": "(sem)", "": "(sem)"}
    )

    # ---- Filtros locais ----
    f1, f2, f3 = st.columns([1, 1, 1])
    with f1:
        minifabs = sorted(df_far["Mini_fab"].unique())
        sel_mf = st.multiselect("Mini Fábrica", minifabs, default=minifabs,
                                key="farol_mf")
    with f2:
        obs_opts = sorted(df_far["Obsolescencia"].dropna().unique())
        sel_obs = st.multiselect("Obsolescência", obs_opts, default=obs_opts,
                                 key="farol_obs")
    with f3:
        sel_cor = st.multiselect("Farol", ["verde", "amarelo", "vermelho"],
                                 default=["verde", "amarelo", "vermelho"],
                                 key="farol_cor_filter",
                                 format_func=lambda x: f"{FAROL_EMOJI[x]} {FAROL_LABEL[x]}")

    df_show = df_far[
        df_far["Mini_fab"].isin(sel_mf)
        & df_far["Obsolescencia"].isin(sel_obs)
        & df_far["Farol_cor"].isin(sel_cor)
    ].copy()

    # ---- Cards de contagem por cor ----
    cnt = df_show["Farol_cor"].value_counts().to_dict()
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-label">Total no recorte</div>'
            f'<div class="kpi-value">{len(df_show)}</div></div>',
            unsafe_allow_html=True,
        )
    for col, (cor, lbl) in zip([k2, k3, k4],
                               [("verde", "🟢 Manter"),
                                ("amarelo", "🟡 Acompanhar"),
                                ("vermelho", "🔴 Substituir")]):
        with col:
            n = cnt.get(cor, 0)
            pct = (n / len(df_show) * 100) if len(df_show) else 0
            st.markdown(
                f'<div class="kpi-card"><div class="kpi-label">{lbl}</div>'
                f'<div class="kpi-value">{n}<span class="kpi-unit"> · {pct:.0f}%</span></div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ---- Gráfico distribuição β por cor ----
    col_l, col_r = st.columns([2, 3])
    with col_l:
        st.subheader("Distribuição do farol")
        dist = (df_show["Farol_cor"]
                .value_counts()
                .reindex(["verde", "amarelo", "vermelho"], fill_value=0))
        fig = go.Figure(go.Bar(
            x=[FAROL_LABEL[c] for c in dist.index],
            y=dist.values,
            marker_color=[GREEN_OK, YELLOW_WARN, RED_ALERT],
            text=dist.values,
            textposition="outside",
            textfont=dict(color=TEXT_PRIMARY, size=14),
        ))
        fig.update_layout(
            **PLOTLY_LAYOUT, height=380,
            showlegend=False, yaxis_title="Nº de ativos",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("β × Idade do ativo (cor = farol)")
        cor_map = {"verde": GREEN_OK, "amarelo": YELLOW_WARN, "vermelho": RED_ALERT}
        d = df_show.dropna(subset=["Beta", "Idade_anos"])
        fig = go.Figure()
        for cor in ["verde", "amarelo", "vermelho"]:
            d_c = d[d["Farol_cor"] == cor]
            fig.add_trace(go.Scatter(
                x=d_c["Idade_anos"], y=d_c["Beta"],
                mode="markers",
                marker=dict(color=cor_map[cor], size=9, opacity=0.75,
                            line=dict(color=BG_DARK, width=1)),
                name=FAROL_LABEL[cor],
                text=d_c["TAG"],
                hovertemplate="<b>%{text}</b><br>Idade: %{x} anos<br>β: %{y:.2f}<extra></extra>",
            ))
        # Linhas de referência das faixas de β
        for thr, lbl in [(0.9, "β=0,9"), (1.2, "β=1,2"), (1.5, "β=1,5")]:
            fig.add_hline(y=thr, line_dash="dot", line_color=TEXT_MUTED,
                          annotation_text=lbl, annotation_position="right",
                          annotation_font_color=TEXT_MUTED)
        fig.update_layout(
            **PLOTLY_LAYOUT, height=380,
            xaxis_title="Idade (anos)", yaxis_title="β (Weibull)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ---- Tabela detalhada ----
    st.subheader("Detalhamento por ativo")
    cols_tab = ["Farol", "TAG", "Denominacao", "Mini_fab", "Beta", "Fase β",
                "Obsolescencia", "Idade_anos", "MTBF_h", "Custo_manut_total",
                "Agravantes", "Recomendação"]
    df_disp = df_show.assign(
        _ord=df_show["Farol_cor"].map({"vermelho": 0, "amarelo": 1, "verde": 2}),
    ).sort_values(["_ord", "Beta"], ascending=[True, False])[cols_tab]

    st.dataframe(
        df_disp,
        hide_index=True,
        use_container_width=True,
        height=480,
        column_config={
            "Farol": st.column_config.TextColumn("Farol", width="small"),
            "Denominacao": st.column_config.TextColumn("Denominação"),
            "Mini_fab": st.column_config.TextColumn("Mini Fáb"),
            "Beta": st.column_config.NumberColumn("β", format="%.2f"),
            "Obsolescencia": st.column_config.TextColumn("Obsolescência"),
            "Idade_anos": st.column_config.NumberColumn("Idade (anos)", format="%d"),
            "MTBF_h": st.column_config.NumberColumn("MTBF (h)", format="%.0f"),
            "Custo_manut_total": st.column_config.NumberColumn(
                "Custo Manut. Total", format="R$ %.0f"
            ),
        },
    )

    st.download_button(
        "📥 Exportar farol (.csv)",
        data=df_disp.to_csv(index=False).encode("utf-8"),
        file_name=f"farol_priorizacao_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        key="dl_farol",
    )


# =============================================================================
# ABA 8 — ROI / LCC (replica fórmulas do Excel)
# =============================================================================
with tab8:
    st.subheader("Análise de Substituição × Manutenção (LCC 7 anos)")
    st.markdown(
        f'<p class="subtle">Compara, em valor presente líquido, o cenário de '
        f"<b>manter</b> vs <b>substituir</b> o ativo no horizonte de {HORIZONTE_ANOS} "
        f"anos. Réplica das fórmulas do workbook (NPV + CAE + ROI). Falhas projetadas "
        f"linearmente; redução de custo com novo = 80%; taxa de desconto = 10%.</p>",
        unsafe_allow_html=True,
    )

    # ---- Top N por custo de manutenção acumulado ----
    st.markdown("##### Top 5 — maior custo de manutenção acumulado")
    top5 = (df_excel.dropna(subset=["Custo_manut_total"])
            .nlargest(5, "Custo_manut_total"))
    c_cols = st.columns(5)
    for col, (_, r) in zip(c_cols, top5.iterrows()):
        cor = farol_v2(r["Beta"], r["Obsolescencia"])["cor"]
        with col:
            st.markdown(
                f'<div class="kpi-card">'
                f'<div class="kpi-label">{FAROL_EMOJI[cor]} {r["TAG"]}</div>'
                f'<div class="kpi-value">R$ {r["Custo_manut_total"]/1000:.0f}'
                f'<span class="kpi-unit">k</span></div>'
                f'<div style="color:{TEXT_MUTED}; font-size:11px; margin-top:6px;">'
                f'β={r["Beta"]:.2f} · {int(r["Idade_anos"])}a · {r["Mini_fab"] or "-"}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ---- Seletor de ativo ----
    df_lcc = df_excel.dropna(subset=["Valor_aquisicao", "Custo_corretiva",
                                      "Custo_preventiva_mensal", "Tempo_total",
                                      "Tempo_missao", "Qtd_falhas"])
    sel_tag = st.selectbox(
        "Ativo para análise detalhada",
        options=df_lcc["TAG"].tolist(),
        index=0 if len(df_lcc) else None,
        format_func=lambda t: f"{t} — {df_lcc[df_lcc['TAG']==t]['Denominacao'].iloc[0]}",
        key="lcc_tag",
    )

    if sel_tag:
        r = df_lcc[df_lcc["TAG"] == sel_tag].iloc[0]
        res = calcular_lcc(
            valor_aquisicao=r["Valor_aquisicao"],
            valor_residual=r["Valor_residual"],
            custo_manut_total=r["Custo_manut_total"],
            falhas_por_ano=r["Falhas_por_ano"],
            custo_corretiva=r["Custo_corretiva"],
            custo_preventiva_mensal=r["Custo_preventiva_mensal"],
            taxa=r["Taxa"],
            reducao_manut=r["Reducao_manut"],
            inflacao_acrescimo=r["Inflacao_acrescimo"],
        )
        f = farol_v2(r["Beta"], r["Obsolescencia"])

        # KPIs do cenário
        k1, k2, k3, k4, k5 = st.columns(5)
        kpis_def = [
            ("Custo de Manter (7a NPV)", f'R$ {abs(res["npv_atual"])/1000:.0f}k'),
            ("Custo de Substituir (7a NPV)",
             f'R$ {abs(res["npv_novo"] + res["capex_novo"])/1000:.0f}k'),
            ("Potencial Ganho", f'R$ {res["potencial_ganho"]/1000:+.0f}k'),
            ("Payback (anos)",
             f'{res["payback_anos"]:.1f}' if not pd.isna(res["payback_anos"])
             else "—"),
            ("Farol", f'{FAROL_EMOJI[f["cor"]]} {FAROL_LABEL[f["cor"]]}'),
        ]
        for col, (lbl, val) in zip([k1, k2, k3, k4, k5], kpis_def):
            with col:
                st.markdown(
                    f'<div class="kpi-card">'
                    f'<div class="kpi-label">{lbl}</div>'
                    f'<div class="kpi-value" style="font-size:22px;">{val}</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<br>", unsafe_allow_html=True)

        # Projeção 7 anos: atual vs novo
        ano_aq = int(r["Ano_aquisicao"]) if pd.notna(r["Ano_aquisicao"]) else 2023
        anos_proj = np.arange(2024, 2024 + HORIZONTE_ANOS)
        fluxo_atual_abs = np.abs(res["fluxo_atual"])
        fluxo_novo_abs = np.abs(res["fluxo_novo"])

        col_a, col_b = st.columns([3, 2])

        with col_a:
            st.markdown("##### Custo anual projetado (7 anos)")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=anos_proj, y=fluxo_atual_abs,
                mode="lines+markers", name="Manter",
                line=dict(color=RED_ALERT, width=3),
                marker=dict(size=8),
            ))
            fig.add_trace(go.Scatter(
                x=anos_proj, y=fluxo_novo_abs,
                mode="lines+markers", name="Substituir",
                line=dict(color=GREEN_OK, width=3),
                marker=dict(size=8),
            ))
            # Regressão linear sobre o cenário atual (visualmente)
            z = np.polyfit(np.arange(HORIZONTE_ANOS), fluxo_atual_abs, 1)
            tend = np.poly1d(z)
            fig.add_trace(go.Scatter(
                x=anos_proj, y=tend(np.arange(HORIZONTE_ANOS)),
                mode="lines", line=dict(color=VENT_TEAL, dash="dash"),
                name=f"Tendência atual (+R$ {z[0]/1000:.1f}k/ano)",
            ))
            fig.update_layout(
                **PLOTLY_LAYOUT, height=380,
                xaxis_title="Ano", yaxis_title="Custo anual (R$)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            st.markdown("##### Decomposição financeira")
            tbl_fin = pd.DataFrame({
                "Item": [
                    "VPL Manter (7a)",
                    "VPL Novo — Manutenção (7a)",
                    "CAPEX do ativo novo",
                    "Valor Residual recuperado",
                    "Potencial Ganho",
                    "CAE Atual (R$/ano)",
                    "CAE Novo (R$/ano)",
                    "ROI (estilo Excel)",
                ],
                "Valor": [
                    f'R$ {res["npv_atual"]:,.0f}',
                    f'R$ {res["npv_novo"]:,.0f}',
                    f'R$ {res["capex_novo"]:,.0f}',
                    f'R$ {res["valor_residual"]:,.0f}',
                    f'R$ {res["potencial_ganho"]:+,.0f}',
                    f'R$ {res["cae_atual"]:,.0f}',
                    f'R$ {res["cae_novo"]:,.0f}',
                    f'{res["roi"]:.2%}' if not pd.isna(res["roi"]) else "—",
                ],
            })
            st.dataframe(tbl_fin, hide_index=True, use_container_width=True,
                         height=360)

        st.caption(
            f'🛈 Inputs do ativo: β={r["Beta"]:.2f}, ano aquisição={ano_aq}, '
            f'valor aquisição=R$ {r["Valor_aquisicao"]:,.0f}, residual=R$ '
            f'{r["Valor_residual"]:,.0f}, custo corretiva=R$ {r["Custo_corretiva"]:,.0f}/falha, '
            f'preventiva=R$ {r["Custo_preventiva_mensal"]:,.0f}/mês, '
            f'falhas/ano≈{r["Falhas_por_ano"]:.1f}.'
        )

    st.markdown("---")

    # ---- Bubble: Custo médio × MTBF × Tempo de vida ----
    st.subheader("Custo médio × MTBF × Idade do ativo")
    st.markdown(
        f'<p class="subtle">Visualização sugerida pelo Diego: cada bolha é um ativo. '
        f"X = idade, Y = MTBF nominal, tamanho = custo médio anual de manutenção, "
        f"cor = farol. Quanto mais à direita-abaixo-grande-vermelho, mais crítico.</p>",
        unsafe_allow_html=True,
    )

    df_bub = df_far.dropna(subset=["MTBF_h", "Idade_anos", "Custo_anual_medio"])
    df_bub = df_bub[df_bub["MTBF_h"] > 0]
    if len(df_bub) > 0:
        cor_map = {"verde": GREEN_OK, "amarelo": YELLOW_WARN, "vermelho": RED_ALERT}
        # tamanho normalizado (sqrt para não explodir)
        size_raw = np.sqrt(df_bub["Custo_anual_medio"].clip(lower=1))
        size_norm = 8 + (size_raw - size_raw.min()) / (size_raw.max() - size_raw.min() + 1e-9) * 40

        fig = go.Figure()
        for cor in ["verde", "amarelo", "vermelho"]:
            d_c = df_bub[df_bub["Farol_cor"] == cor]
            if d_c.empty:
                continue
            s_c = size_norm[df_bub["Farol_cor"] == cor]
            fig.add_trace(go.Scatter(
                x=d_c["Idade_anos"], y=d_c["MTBF_h"],
                mode="markers",
                marker=dict(
                    color=cor_map[cor],
                    size=s_c,
                    opacity=0.65,
                    line=dict(color=BG_DARK, width=1),
                ),
                name=FAROL_LABEL[cor],
                text=d_c["TAG"],
                customdata=np.column_stack([d_c["Custo_anual_medio"], d_c["Beta"]]),
                hovertemplate=(
                    "<b>%{text}</b><br>Idade: %{x} anos<br>"
                    "MTBF: %{y:.0f} h<br>Custo médio: R$ %{customdata[0]:,.0f}/ano<br>"
                    "β: %{customdata[1]:.2f}<extra></extra>"
                ),
            ))
        fig.update_yaxes(type="log")
        fig.update_layout(
            **PLOTLY_LAYOUT, height=520,
            xaxis_title="Idade do ativo (anos)",
            yaxis_title="MTBF nominal (horas) — escala log",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)


# =============================================================================
# FOOTER
# =============================================================================
st.markdown("---")
st.markdown(
    f'<div style="text-align:center; padding: 20px 0;">'
    f'<span class="subtle">Protótipo desenvolvido por </span>'
    f'<span class="brand-vent">vent\'</span>'
    f'<span class="subtle"> para </span>'
    f'<span class="brand-stihl">STIHL</span>'
    f'<span class="subtle"> · Solução de Visualização de Dados de Análise de Confiabilidade — v0.1</span>'
    f"</div>",
    unsafe_allow_html=True,
)
