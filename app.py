import json
import urllib.parse

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import plotly.graph_objects as go

# \u2500\u2500 Page config \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
st.set_page_config(
    page_title="Hunter Argentina \u00b7 Reporte INB",
    page_icon="\ud83d\udcca",
    layout="wide",
)

# \u2500\u2500 Constantes \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = "1wtXzHb0Jl8OZK0_K5BZpI4GdNcsbi9Iom_h5tUE4C4w"
SHEET_NAME     = "DATOS INB"

TURNO_MANUAL = {
    "1348": "TM", "7417": "TM", "7423": "TM", "7443": "TM", "9140": "TM",
    "9281": "TM", "9297": "TM", "9321": "TM", "9372": "TM",
}

# \u2500\u2500 Color gradient \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
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

# \u2500\u2500 Data loading (cache 30 min) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
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

    headers = data[0] + ["COL_AA", "TURNO", "SKILL"]
    df = pd.DataFrame(data[1:], columns=headers)

    df["FECHA"]       = df["FECHA"].astype(str).str.strip()
    df["ANI_TELEFONO"]= df["ANI_TELEFONO"].astype(str).str.strip()
    df["TURNO"]       = df["TURNO"].fillna("").astype(str).str.strip()
    df["SKILL"]       = df["SKILL"].fillna("").astype(str).str.strip()

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
    agente_skill  = df_raw.groupby("COD_AGENTE")["SKILL"].agg(skill_primario)
    agente_turno  = df_raw.groupby("COD_AGENTE")["TURNO"].agg(skill_primario).copy()
    agente_nombre = df_raw.groupby("COD_AGENTE")["USUARIO"].agg(lambda s: s.mode()[0])

    for cod, turno in TURNO_MANUAL.items():
        agente_turno[cod] = turno

    pivot = (
        df_raw.groupby(["COD_AGENTE", "FECHA"])["ANI_TELEFONO"]
        .nunique().reset_index().rename(columns={"ANI_TELEFONO": "COUNT"})
    )
    pw = pivot.pivot_table(
        index="COD_AGENTE", columns="FECHA", values="COUNT", fill_value=0
    ).reset_index()
    pw.columns.name = None

    pw["SKILL"]  = pw["COD_AGENTE"].map(agente_skill)
    pw["TURNO"]  = pw["COD_AGENTE"].map(agente_turno)
    pw["USUARIO"]= pw["COD_AGENTE"].map(agente_nombre)

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
        fechas    = fechas_cols,
        hunter    = hunter_rows,
        total_dia = [int(total_dia[f]) for f in fechas_cols],
        total_inb = [int(total_inb[f]) for f in fechas_cols],
        total_desb= [int(total_desb[f]) for f in fechas_cols],
        pct_desb  = [float(pct_desb[f]) for f in fechas_cols],
        pct_inb   = [float(pct_inb[f])  for f in fechas_cols],
        pct_tm=pct_tm, pct_tt=pct_tt,
        prom_desb=prom_desb, prom_inb=prom_inb,
        prom_tm=prom_tm, prom_tt=prom_tt,
    )

# \u2500\u2500 CSS global \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500