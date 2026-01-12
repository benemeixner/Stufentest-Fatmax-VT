# app_cpet_step.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_plotly_events import plotly_events

from cpet_xml_reader import read_metasoftstudio_xml
from cpet_analysis import assign_stages, stage_lastwindow_means, add_fatox_table

st.set_page_config(page_title="Stufentest: FatMax & VT1/VT2", layout="wide")
st.title("Stufentest (3-min Stufen): Offset → FatMax (letzte 30 s) → Wasserman (VT1/VT2)")

uploaded = st.file_uploader("MetasoftStudio XML hochladen", type=["xml"])

st.sidebar.header("Stufen-Parameter")
offset_s = st.sidebar.number_input("Versatz zur 1. Stufe (Sekunden)", min_value=0.0, value=0.0, step=1.0)
stage_duration_s = st.sidebar.number_input("Stufendauer (s)", min_value=30.0, value=180.0, step=10.0)
start_power_w = st.sidebar.number_input("Startleistung (W)", min_value=0.0, value=75.0, step=5.0)
step_power_w = st.sidebar.number_input("Leistungsinkrement pro Stufe (W)", min_value=0.0, value=25.0, step=5.0)
last_window_s = st.sidebar.number_input("Fenster: letzte Sekunden pro Stufe", min_value=5.0, value=30.0, step=5.0)

if uploaded is None:
    st.info("Bitte XML hochladen. Danach kannst du Offset & Stufenparameter einstellen.")
    st.stop()

# ---------- Parse ----------
try:
    raw = read_metasoftstudio_xml(uploaded.getvalue())
except Exception as e:
    st.error(f"Konnte XML nicht lesen: {e}")
    st.stop()

# ---------- Stage alignment ----------
df = assign_stages(raw, offset_s=offset_s, stage_duration_s=stage_duration_s, start_power_w=start_power_w, step_power_w=step_power_w)

# Numeric coercion
for c in df.columns:
    if c not in ["t", "Phase", "Marker"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

df = df[df["stage_idx"] >= 0].copy()
if df.empty:
    st.warning("Nach dem Offset wurden keine Daten einer Stufe zugeordnet. Prüfe den Versatz.")
    st.stop()

df["t_rel_s"] = df["t_s"] - float(offset_s)

# --- 1 Hz aggregation + 30 s rolling smoothing for Wasserman time series ---
df_1hz = df.copy()
df_1hz["sec"] = np.floor(df_1hz["t_rel_s"]).astype(int)

# IMPORTANT: exclude t_rel_s from aggregation to avoid duplicate column name later
exclude_cols = {"t", "Phase", "Marker", "t_rel_s"}
num_cols = [c for c in df_1hz.columns if c not in exclude_cols]

df_1hz = df_1hz.groupby("sec", as_index=False)[num_cols].mean(numeric_only=True)
df_1hz["t_rel_s"] = df_1hz["sec"].astype(float)
df_1hz = df_1hz.drop(columns=["sec"])

roll_cols = [c for c in df_1hz.columns if c != "t_rel_s"]
df_smooth = df_1hz.sort_values("t_rel_s").copy()
df_smooth[roll_cols] = df_smooth[roll_cols].rolling(window=30, min_periods=5, center=True).mean()

max_t = float(df_1hz["t_rel_s"].max())

# ---------- Stage table (last window means) ----------
stage_tbl = stage_lastwindow_means(df, stage_duration_s=stage_duration_s, last_window_s=last_window_s)
stage_tbl = add_fatox_table(stage_tbl)

st.subheader("Stufenübersicht (Mittelwerte der letzten Sekunden pro Stufe)")
show_cols = [c for c in ["stage_idx","stage_power_w","n_samples","V'O2","V'CO2","V'E","RER","V'E/V'O2","V'E/V'CO2",
                         "PETO2","PETCO2","HF","FatOx_g_min","CHOox_g_min"] if c in stage_tbl.columns]
st.dataframe(stage_tbl[show_cols], use_container_width=True)

# ---------- FatMax: clickable Plotly scatter ----------
st.subheader("FatMax: Punkte (FatOx vs Leistung) – Punkt anklicken zum Auswählen")

if "FatOx_g_min" in stage_tbl.columns and stage_tbl["FatOx_g_min"].notna().any():
    if "fatmax_stage" not in st.session_state:
        st.session_state.fatmax_stage = int(stage_tbl.loc[stage_tbl["FatOx_g_min"].idxmax(), "stage_idx"])

    plot_df = stage_tbl.dropna(subset=["stage_power_w", "FatOx_g_min"]).copy()
    plot_df["selected"] = plot_df["stage_idx"].astype(int) == int(st.session_state.fatmax_stage)

    fat_max = float(np.nanmax(plot_df["FatOx_g_min"])) if len(plot_df) else 0.0
    fat_min = float(np.nanmin(plot_df["FatOx_g_min"])) if len(plot_df) else 0.0
    if fat_max > 0:
        y_low = 0.0
        y_high = max(0.2, fat_max * 1.2)
    else:
        y_low = fat_min * 1.2
        y_high = 0.5

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=plot_df["stage_power_w"],
        y=plot_df["FatOx_g_min"],
        mode="markers+lines",
        text=[f"Stage {int(s)}" for s in plot_df["stage_idx"]],
        marker=dict(size=[18 if sel else 10 for sel in plot_df["selected"]]),
        hovertemplate="Leistung: %{x:.0f} W<br>FatOx: %{y:.3f} g/min<br>%{text}<extra></extra>",
        name="FatOx"
    ))
    fig.update_layout(
        xaxis_title="Leistung (W)",
        yaxis_title="FatOx (g/min)",
        yaxis=dict(range=[y_low, y_high]),
        height=420,
        margin=dict(l=40, r=20, t=30, b=40),
    )

    clicked = plotly_events(fig, click_event=True, hover_event=False, select_event=False, override_height=420, override_width="100%")
    if clicked:
        point_idx = clicked[0].get("pointIndex", None)
        if point_idx is not None and 0 <= point_idx < len(plot_df):
            st.session_state.fatmax_stage = int(plot_df.iloc[point_idx]["stage_idx"])

    fatmax_row = stage_tbl[stage_tbl["stage_idx"].astype(int) == int(st.session_state.fatmax_stage)].iloc[0]
    st.write(
        f"**Ausgewählte FatMax-Stufe:** {int(fatmax_row['stage_idx'])}  | "
        f"**Leistung:** {fatmax_row['stage_power_w']:.0f} W  | "
        f"**FatOx:** {fatmax_row['FatOx_g_min']:.3f} g/min"
    )
else:
    st.info("FatOx konnte nicht berechnet werden (VO2/VCO2 fehlen) oder ist komplett NaN.")

# ---------- Wasserman 9-panel (smoothed) ----------
st.subheader("Wasserman 9-Felder (30s rolling mean) – VT1/VT2 setzen")

vt1_s = st.slider("VT1 Zeitpunkt (s, relativ zum Beginn der 1. Stufe)", min_value=0.0, max_value=max_t, value=min(300.0, max_t), step=1.0)
vt2_s = st.slider("VT2 Zeitpunkt (s, relativ zum Beginn der 1. Stufe)", min_value=0.0, max_value=max_t, value=min(600.0, max_t), step=1.0)

def add_vlines(fig):
    fig.add_vline(x=vt1_s, line_width=2)
    fig.add_vline(x=vt2_s, line_width=2)
    return fig

def timeseries_fig(y_cols, title, yaxis_title=None):
    fig = go.Figure()
    for col in y_cols:
        if col in df_smooth.columns:
            fig.add_trace(go.Scatter(x=df_smooth["t_rel_s"], y=df_smooth[col], mode="lines", name=col))
    fig.update_layout(
        title=title,
        height=260,
        margin=dict(l=40, r=20, t=35, b=35),
        xaxis_title="Zeit (s)",
        yaxis_title=yaxis_title or "",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return add_vlines(fig)

def vslope_fig():
    fig = go.Figure()
    if "V'O2" in df.columns and "V'CO2" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["V'O2"], y=df["V'CO2"],
            mode="markers", marker=dict(size=5, opacity=0.4),
            name="Breath-by-breath"
        ))
    fig.update_layout(
        title="V-Slope (VCO2 vs VO2)",
        height=260,
        margin=dict(l=40, r=20, t=35, b=35),
        xaxis_title="VO2 (L/min)",
        yaxis_title="VCO2 (L/min)",
        showlegend=False
    )
    return fig

panel_figs = [
    vslope_fig(),
    timeseries_fig(["V'O2", "V'CO2"], "VO2 & VCO2", "L/min"),
    timeseries_fig(["V'E"], "Ventilation (VE)", "L/min"),
    timeseries_fig(["RER"], "RER", ""),
    timeseries_fig(["V'E/V'O2", "V'E/V'CO2"], "Ventilatory equivalents", ""),
    timeseries_fig(["PETO2", "PETCO2"], "End-tidal O2/CO2", "mmHg"),
    timeseries_fig(["VT", "AF"], "Tidal volume & breathing frequency", ""),
    timeseries_fig(["HF"], "Heart rate", "bpm"),
    timeseries_fig(["V'O2/kg", "V'O2/HF"], "Relative VO2 & O2-pulse", ""),
]

for i in range(0, 9, 3):
    c1, c2, c3 = st.columns(3)
    c1.plotly_chart(panel_figs[i], use_container_width=True)
    c2.plotly_chart(panel_figs[i+1], use_container_width=True)
    c3.plotly_chart(panel_figs[i+2], use_container_width=True)

# ---------- VT power interpolation ----------
def vt_power_interpolated(t_rel_s: float) -> float:
    n = int(np.floor(t_rel_s / float(stage_duration_s)))
    frac = (t_rel_s - n * float(stage_duration_s)) / float(stage_duration_s)
    frac = float(np.clip(frac, 0.0, 1.0))
    prev_power = float(start_power_w + step_power_w * max(n - 1, 0))
    return prev_power + frac * float(step_power_w)

def stage_at_time(t_rel_s: float) -> int:
    return int(np.floor(t_rel_s / float(stage_duration_s)))

p_vt1 = vt_power_interpolated(vt1_s)
p_vt2 = vt_power_interpolated(vt2_s)
st_vt1 = stage_at_time(vt1_s)
st_vt2 = stage_at_time(vt2_s)

st.subheader("VT1 / VT2 Zusammenfassung (Leistung interpoliert)")
m1, m2 = st.columns(2)
m1.metric("VT1", f"{p_vt1:.1f} W  (Zeit {vt1_s:.0f} s, in Stufe {st_vt1})")
m2.metric("VT2", f"{p_vt2:.1f} W  (Zeit {vt2_s:.0f} s, in Stufe {st_vt2})")

st.caption("Interpolation: innerhalb der aktuellen 3-min Stufe wird zwischen **vorheriger** und **aktueller** Stufe linear interpoliert (Lag-Konvention).")

csv_bytes = stage_tbl.to_csv(index=False).encode("utf-8")
st.download_button("Stufentabelle (letzte Sekunden) als CSV herunterladen", data=csv_bytes, file_name="stufen_last_window.csv", mime="text/csv")
