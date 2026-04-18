import json
import urllib.parse

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import plotly.graph_objects as go

# Page config
st.set_page_config(
    page_title="Hunter Argentina - Reporte INB",
    page_icon="📊",
    layout="wide",
)

# Constantes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = "1wtXzHb0Jl8OZK0_K5BZpI4GdNcsbi9Iom_h5tUE4C4w"
SHEET_NAME     = "DATOS INB"


# Color gradient
def lerp(a, b, t):
    return int(a + (b - a) * t)

def color_hex(val):
    v = float(val)
    if v <= 10:
        return "#22c55e"
    t = min((v - 10) / 30, 1.0)
    return f"#{lerp(0xf5,0xef,t):02x}{lerp(0x9e,0x44,t):02x}{lerp(0x0b,0x44,t):02x}"

def style_pct(val):
    try:
        v = float(str(val).replace("%", ""))
    except:
        return ""
    c = color_hex(v)
    return f"color: {c}; font-weight: 700"

# Data loading (cache 30 min)
@st.cache_data(ttl=1800)
def load_data():
    if "GOOGLE_CREDENTIALS" in st.secrets:
        creds_info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credenciales.json", scopes=SCOPES)

    client = gspread.authorize(creds)
    sheet  = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    data   = sheet.get("A1:AC")

    raw_headers = data[0]
    extra   = [c for c in ["COL_AA", "TURNO", "SKILL"] if c not in raw_headers]
    headers = raw_headers + extra
    n_cols  = len(headers)
    rows    = [row + [""] * (n_cols - len(row)) for row in data[1:]]
    df      = pd.DataFrame(rows, columns=headers)

    df["FECHA"]        = df["FECHA"].astype(str).str.strip()
    df["ANI_TELEFONO"] = df["ANI_TELEFONO"].astype(str).str.strip()
    df["TURNO"]        = df["TURNO"].fillna("").astype(str).str.strip()
    df["SKILL"]        = df["SKILL"].fillna("").astype(str).str.strip()

    df = df[df["FECHA"].str.match(r"^\d{8}$")]
    df["FECHA"] = pd.to_datetime(df["FECHA"], format="%Y%m%d").dt.strftime("%d/%m/%Y")

    df_entrante = df[df["DIRECCION"].str.strip().str.upper() == "ENTRANTE"].copy()
    df_raw      = df_entrante.copy()

    def extraer_codigo(usuario):
        p = str(usuario).split("-")
        return p[0].strip() if p[0].strip().isdigit() else "0"

    def skill_primario(series):
        vals = series[~series.isin(["", "0", "nan"])]
        return vals.mode()[0] if not vals.empty else "0"

    df_raw["COD_AGENTE"] = df_raw["USUARIO"].apply(extraer_codigo)
    agente_nombre = df_raw.groupby("COD_AGENTE")["USUARIO"].agg(lambda s: s.mode()[0])

    # Lee el lookup de agentes desde columnas AE (SKILL), AF (TURNO), AG (COD)
    lookup_rows  = sheet.get("AE:AG")
    agent_lookup = {}
    for row in lookup_rows:
        if len(row) >= 3 and str(row[2]).strip().isdigit():
            cod = str(row[2]).strip()
            agent_lookup[cod] = (row[0].strip(), row[1].strip())
    agente_skill = pd.Series({cod: v[0] for cod, v in agent_lookup.items()})
    agente_turno = pd.Series({cod: v[1] for cod, v in agent_lookup.items()})

    pivot = (
        df_raw.groupby(["COD_AGENTE", "FECHA"])["ANI_TELEFONO"]
        .nunique().reset_index().rename(columns={"ANI_TELEFONO": "COUNT"})
    )
    pw = pivot.pivot_table(
        index="COD_AGENTE", columns="FECHA", values="COUNT", fill_value=0
    ).reset_index()
    pw.columns.name = None

    pw["SKILL"]   = pw["COD_AGENTE"].map(agente_skill)
    pw["TURNO"]   = pw["COD_AGENTE"].map(agente_turno)
    pw["USUARIO"] = pw["COD_AGENTE"].map(agente_nombre)

    fechas_cols = sorted([c for c in pw.columns if c not in ["COD_AGENTE","SKILL","TURNO","USUARIO"]])

    mask_inb = pw["SKILL"] == "INB"
    mask_tm  = pw["TURNO"] == "TM"
    mask_tt  = pw["TURNO"] == "TT"

    total_dia  = pw[fechas_cols].sum()
    total_inb  = pw.loc[mask_inb, fechas_cols].sum()
    total_desb = pw.loc[~mask_inb, fechas_cols].sum()
    desb_tm    = pw.loc[mask_tm & ~mask_inb, fechas_cols].sum()
    desb_tt    = pw.loc[mask_tt & ~mask_inb, fechas_cols].sum()

    pct_desb = (total_desb / total_dia * 100).round(2)
    pct_inb  = (total_inb  / total_dia * 100).round(2)

    dias_act  = total_dia[total_dia > 0]
    prom_desb = float((total_desb[dias_act.index] / dias_act * 100).mean().round(2))
    prom_inb  = float((total_inb[dias_act.index]  / dias_act * 100).mean().round(2))

    def pct_list(serie):
        return [round(float(serie[f] / total_dia[f] * 100), 2) if total_dia[f] > 0 else 0.0 for f in fechas_cols]

    pct_tm = pct_list(desb_tm)
    pct_tt = pct_list(desb_tt)

    act   = [total_dia[f] > 0 for f in fechas_cols]
    n_act = max(sum(act), 1)
    prom_tm = round(sum(v for v, a in zip(pct_tm, act) if a) / n_act, 2)
    prom_tt = round(sum(v for v, a in zip(pct_tt, act) if a) / n_act, 2)

    queued_h  = df_entrante[df_entrante["SUB_ESTADO"]=="QUEUED"].groupby("FECHA")["ANI_TELEFONO"].nunique()
    ringing_h = df_entrante[df_entrante["SUB_ESTADO"]=="RINGING"].groupby("FECHA")["ANI_TELEFONO"].nunique()

    hunter_rows = []
    for f in fechas_cols:
        tot  = int(total_dia.get(f, 0))
        desb = int(total_desb.get(f, 0))
        q    = int(queued_h.get(f, 0))
        r    = int(ringing_h.get(f, 0))
        hunter_rows.append({
            "Fecha":          f,
            "Total Llamadas": tot,
            "Total Desborde": desb,
            "% Desborde":     round(desb/tot*100, 1) if tot else 0.0,
            "% QUEUED":       round(q/tot*100, 1)    if tot else 0.0,
            "% RINGING":      round(r/tot*100, 1)    if tot else 0.0,
            "QUEUED_ABS":     q,
            "RINGING_ABS":    r,
        })

    return dict(
        fechas     = fechas_cols,
        hunter     = hunter_rows,
        total_dia  = [int(total_dia[f]) for f in fechas_cols],
        total_inb  = [int(total_inb[f]) for f in fechas_cols],
        total_desb = [int(total_desb[f]) for f in fechas_cols],
        pct_desb   = [float(pct_desb[f]) for f in fechas_cols],
        pct_inb    = [float(pct_inb[f])  for f in fechas_cols],
        pct_tm=pct_tm, pct_tt=pct_tt,
        prom_desb=prom_desb, prom_inb=prom_inb,
        prom_tm=prom_tm, prom_tt=prom_tt,
    )

# CSS global
st.markdown("""
<style>
section[data-testid="stSidebar"] { display: none; }
div[data-testid="stRadio"] label { font-size: 0.78rem !important; }
.kpi-card {
    background: #1e293b; border: 1px solid #334155; border-radius: 12px;
    padding: 14px 18px; height: 100%;
}
.kpi-card .kpi-label { font-size: 0.7rem; color: #94a3b8; text-transform: uppercase; letter-spacing: .05em; }
.kpi-card .kpi-sub   { font-size: 0.62rem; color: #475569; margin-bottom: 6px; }
.kpi-card .kpi-value { font-size: 1.85rem; font-weight: 700; margin-bottom: 4px; }
.kpi-card .kpi-prom  { font-size: 0.68rem; color: #475569; }
.kpi-card .kpi-prom b { color: #22c55e; }
.wa-btn a {
    display: inline-flex; align-items: center; gap: 7px;
    background: #25d366; color: #fff !important; font-weight: 600;
    padding: 9px 18px; border-radius: 8px; text-decoration: none; font-size: 0.85rem;
}
.wa-btn a:hover { background: #1fbb58; }
</style>
""", unsafe_allow_html=True)

# Load
with st.spinner("Cargando datos desde Google Sheets..."):
    d = load_data()

fechas     = d["fechas"]
hunter     = d["hunter"]
hdf        = pd.DataFrame(hunter)
def_idx    = max(len(fechas) - 2, 0)

# ======================================================================
# HUNTER ARGENTINA
# ======================================================================
col_h, col_wa = st.columns([5, 1])
with col_h:
    st.markdown("## 📊 Hunter Argentina")
    st.caption("Llamadas entrantes - Resumen diario")

selected   = st.radio(
    "Dia:", fechas, index=def_idx, horizontal=True, label_visibility="collapsed"
)
idx        = fechas.index(selected)
dia_actual = hunter[idx]

wa_text = (
    f"📊 Hunter Argentina - {dia_actual['Fecha']}\n"
    f"────────────────\n"
    f"Total Llamadas: {dia_actual['Total Llamadas']:,}\n"
    f"Total Desborde: {dia_actual['Total Desborde']:,}\n"
    f"% Desborde: {dia_actual['% Desborde']}%\n"
    f"% QUEUED: {dia_actual['% QUEUED']}%\n"
    f"% RINGING: {dia_actual['% RINGING']}%"
)
wa_url = f"https://wa.me/?text={urllib.parse.quote(wa_text)}"

with col_wa:
    st.markdown(
        f'<div class="wa-btn" style="margin-top:18px"><a href="{wa_url}" target="_blank">📲 Compartir</a></div>',
        unsafe_allow_html=True,
    )

# Metricas del dia seleccionado
st.markdown(f"#### {selected}")
c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("Total Llamadas", f"{dia_actual['Total Llamadas']:,}")
with c2:
    st.metric("Total Desborde", f"{dia_actual['Total Desborde']:,}")

for col, key in [(c3, "% Desborde"), (c4, "% QUEUED"), (c5, "% RINGING")]:
    with col:
        v = dia_actual[key]
        c = color_hex(v)
        st.markdown(
            f'<div style="font-size:.78rem;color:#94a3b8;margin-bottom:4px">{key}</div>'
            f'<div style="font-size:1.85rem;font-weight:700;color:{c}">{v}%</div>',
            unsafe_allow_html=True,
        )

st.markdown("")

# ── Tabla resumen visible (sin expander) ──────────────────────────────
filas = [
    ("LLAMADAS TOTALES", [h["Total Llamadas"] for h in hunter], False),
    ("DESBORDE",         [h["Total Desborde"] for h in hunter], False),
    ("% DESBORDE",       [h["% Desborde"]     for h in hunter], True),
    ("ABANDONADAS",      [h["QUEUED_ABS"]      for h in hunter], False),
    ("% ABANDONADAS",    [h["% QUEUED"]        for h in hunter], True),
    ("RINGING",          [h["RINGING_ABS"]     for h in hunter], False),
    ("% RINGING",        [h["% RINGING"]       for h in hunter], True),
]

det_rows = []
for label, vals, es_pct in filas:
    det_row = {"": label}
    for f, v in zip(fechas, vals):
        det_row[f] = f"{v}%" if es_pct else int(v)
    det_rows.append(det_row)

det_df     = pd.DataFrame(det_rows)
fecha_cols = [c for c in det_df.columns if c != ""]

def style_det(val):
    if isinstance(val, str) and val.endswith("%"):
        try:
            return style_pct(float(val[:-1]))
        except:
            pass
    return ""

st.dataframe(
    det_df.style.map(style_det, subset=fecha_cols),
    use_container_width=True,
    hide_index=True,
)

st.markdown("")

# Tabla todos los dias (colapsable)
with st.expander("📅 Ver todos los dias"):
    styled = (
        hdf[["Fecha","Total Llamadas","Total Desborde","% Desborde","% QUEUED","% RINGING"]]
        .style
        .map(style_pct, subset=["% Desborde", "% QUEUED", "% RINGING"])
        .format({
            "Total Llamadas": "{:,}", "Total Desborde": "{:,}",
            "% Desborde": "{}%", "% QUEUED": "{}%", "% RINGING": "{}%",
        })
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()

# ======================================================================
# ANALISIS INB (colapsable)
# ======================================================================
with st.expander("📈 Ver analisis completo de desborde INB"):

    inb_sel = st.radio(
        "Dia:", fechas, index=def_idx, horizontal=True,
        label_visibility="collapsed", key="inb_radio"
    )
    inb_idx = fechas.index(inb_sel)

    st.markdown("")

    # KPI cards
    k1, k2, k3, k4 = st.columns(4)

    def kpi_card(col, label, sub, val, prom):
        c = color_hex(val)
        with col:
            st.markdown(
                f'<div class="kpi-card">'
                f'<div class="kpi-label">{label}</div>'
                f'<div class="kpi-sub">{sub}</div>'
                f'<div class="kpi-value" style="color:{c}">{val}%</div>'
                f'<div class="kpi-prom">Promedio: <b>{prom}%</b></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    kpi_card(k1, "% Desborde TM", "Turno Manana",  d["pct_tm"][inb_idx],   d["prom_tm"])
    kpi_card(k2, "% Desborde TT", "Turno Tarde",   d["pct_tt"][inb_idx],   d["prom_tt"])
    kpi_card(k3, "% Desborde Total","TM + TT",      d["pct_desb"][inb_idx], d["prom_desb"])
    with k4:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">Dias analizados</div>'
            f'<div class="kpi-sub">&nbsp;</div>'
            f'<div class="kpi-value" style="color:#f59e0b">{len(fechas)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Trend chart
    def pt_colors(vals):
        return [color_hex(v) for v in vals]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fechas, y=d["pct_tm"], name="TM",
        line=dict(color="#3b82f6", width=2),
        marker=dict(size=6, color=pt_colors(d["pct_tm"])),
    ))
    fig.add_trace(go.Scatter(
        x=fechas, y=d["pct_tt"], name="TT",
        line=dict(color="#f97316", width=2),
        marker=dict(size=6, color=pt_colors(d["pct_tt"])),
    ))
    fig.add_trace(go.Scatter(
        x=fechas, y=[d["prom_desb"]] * len(fechas), name="Promedio",
        line=dict(color="#22c55e", width=1.5, dash="dash"), mode="lines",
    ))
    fig.add_trace(go.Scatter(
        x=fechas, y=[10] * len(fechas), name="Limite 10%",
        line=dict(color="#ef4444", width=1, dash="dot"), mode="lines",
    ))
    fig.update_layout(
        paper_bgcolor="#1e293b", plot_bgcolor="#1e293b",
        font=dict(color="#94a3b8", size=11),
        height=220, margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis=dict(gridcolor="#172033", tickfont=dict(size=10)),
        yaxis=dict(gridcolor="#334155", ticksuffix="%", tickfont=dict(size=10)),
    )
    st.plotly_chart(fig, use_container_width=True)
