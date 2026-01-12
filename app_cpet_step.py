# app_cpet_step.py
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

from cpet_xml_reader import read_metasoftstudio_xml
from cpet_analysis import assign_stages, stage_last30_means, add_fatox_table

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

# Numeric coercion for common cols
for c in ["V'O2","V'CO2","V'E","RER","V'E/V'O2","V'E/V'CO2","VT","AF","HF","V'O2/kg","V'O2/HF"]:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

df = df[df["stage_idx"] >= 0].copy()
if df.empty:
    st.warning("Nach dem Offset wurden keine Daten einer Stufe zugeordnet. Prüfe den Versatz.")
    st.stop()

# Relative time: 0 = Beginn der 1. Stufe (Offset)
df["t_rel_s"] = df["t_s"] - float(offset_s)
max_t = float(df["t_rel_s"].max())

# ---------- Stage table (last window means) ----------
stage_tbl = stage_last30_means(df, stage_duration_s=stage_duration_s, last_window_s=last_window_s)
stage_tbl = add_fatox_table(stage_tbl)

st.subheader("Stufenübersicht (Mittelwerte der letzten Sekunden pro Stufe)")
show_cols = [c for c in ["stage_idx","stage_power_w","n_samples","V'O2","V'CO2","V'E","RER","V'E/V'O2","V'E/V'CO2","HF","FatOx_g_min","CHOox_g_min"] if c in stage_tbl.columns]
st.dataframe(stage_tbl[show_cols], use_container_width=True)

# ---------- FatMax scatter (FatOx vs Power) + selection ----------
st.subheader("FatMax als Punkte gegen Leistung")
if "FatOx_g_min" in stage_tbl.columns:
    # default: max FatOx stage
    default_stage_idx = int(stage_tbl["FatOx_g_min"].fillna(-1e9).idxmax())
    default_stage = int(stage_tbl.loc[default_stage_idx, "stage_idx"])

    power_options = stage_tbl["stage_power_w"].round(0).astype(int).tolist()
    default_power = int(stage_tbl.loc[stage_tbl["stage_idx"] == default_stage, "stage_power_w"].iloc[0])

    selected_power = st.select_slider(
        "FatMax auswählen (Leistung, W) — schau dir die Punkte an und wähle die passende Stufe",
        options=power_options,
        value=default_power
    )
    # map back to stage
    fatmax_row = stage_tbl.loc[stage_tbl["stage_power_w"].round(0).astype(int) == int(selected_power)].iloc[0]
    fatmax_stage = int(fatmax_row["stage_idx"])

    plot_df = stage_tbl.copy()
    plot_df["selected"] = (plot_df["stage_idx"] == fatmax_stage)

    pts = alt.Chart(plot_df).mark_point(size=90).encode(
        x=alt.X("stage_power_w:Q", title="Leistung (W)"),
        y=alt.Y("FatOx_g_min:Q", title="FatOx (g/min)"),
        tooltip=["stage_idx", alt.Tooltip("stage_power_w:Q", format=".0f"), alt.Tooltip("FatOx_g_min:Q", format=".3f")]
    )

    line = alt.Chart(plot_df).mark_line().encode(
        x="stage_power_w:Q",
        y="FatOx_g_min:Q"
    )

    highlight = alt.Chart(plot_df[plot_df["selected"]]).mark_point(size=180).encode(
        x="stage_power_w:Q",
        y="FatOx_g_min:Q"
    )

    st.altair_chart((line + pts + highlight).interactive(), use_container_width=True)
    st.write(f"**Ausgewählte FatMax-Stufe:** {fatmax_stage}  | **Leistung:** {fatmax_row['stage_power_w']:.0f} W  | **FatOx:** {fatmax_row['FatOx_g_min']:.3f} g/min")
else:
    st.info("FatOx konnte nicht berechnet werden (VO2/VCO2 fehlen). Du kannst trotzdem VT1/VT2 bestimmen.")

# ---------- Wasserman-style 9-field view ----------
st.subheader("Wasserman (9 Felder) – visuelle Bestimmung von VT1 / VT2")
st.caption("Stelle VT1/VT2 über die Schieberegler ein. Linien werden in allen Zeit-Plots angezeigt.")

vt1_s = st.slider("VT1 Zeitpunkt (s, relativ zum Beginn der 1. Stufe)", min_value=0.0, max_value=max_t, value=min(300.0, max_t), step=1.0)
vt2_s = st.slider("VT2 Zeitpunkt (s, relativ zum Beginn der 1. Stufe)", min_value=0.0, max_value=max_t, value=min(600.0, max_t), step=1.0)

def vline_layer():
    return alt.Chart(pd.DataFrame({"t":[vt1_s, vt2_s]})).mark_rule().encode(x="t:Q")

def line_chart(y, title):
    base = alt.Chart(df).mark_line().encode(
        x=alt.X("t_rel_s:Q", title="Zeit (s)"),
        y=alt.Y(f"{y}:Q", title=title)
    ).properties(title=title, height=200)
    return (base + vline_layer()).interactive()

charts = []

# Panel 1: V-Slope (if available)
if "V'O2" in df.columns and "V'CO2" in df.columns:
    vslope = alt.Chart(df).mark_point(opacity=0.3, size=15).encode(
        x=alt.X("V'O2:Q", title="VO2 (L/min)"),
        y=alt.Y("V'CO2:Q", title="VCO2 (L/min)")
    ).properties(title="V-Slope (VCO2 vs VO2)", height=200).interactive()
    charts.append(vslope)
else:
    charts.append(alt.Chart(pd.DataFrame({"x":[0], "y":[0]})).mark_text(text="VO2/VCO2 nicht verfügbar").properties(height=200))

# Remaining time-based panels
fields = [
    ("V'O2", "VO2 (L/min)"),
    ("V'CO2", "VCO2 (L/min)"),
    ("V'E", "VE (L/min)"),
    ("RER", "RER"),
    ("V'E/V'O2", "VE/VO2"),
    ("V'E/V'CO2", "VE/VCO2"),
    ("HF", "HF (/min)"),
    ("VT", "VT (L)"),
    ("AF", "AF (/min)"),
]

for col, title in fields:
    if col in df.columns and len(charts) < 9:
        charts.append(line_chart(col, title))

# pad to 9 charts if fewer fields exist
while len(charts) < 9:
    charts.append(alt.Chart(pd.DataFrame({"x":[0], "y":[0]})).mark_text(text="(Feld nicht verfügbar)").properties(height=200))

rows3 = [charts[i:i+3] for i in range(0, 9, 3)]
for row in rows3:
    c1, c2, c3 = st.columns(3)
    for c, ch in zip([c1,c2,c3], row):
        c.altair_chart(ch, use_container_width=True)

# ---------- VT1/VT2 as interpolated power ----------
def vt_power_interpolated(t_rel_s: float) -> float:
    """Approximate VT power between two adjacent stages.

    Convention:
    - Determine the *current* stage index n from time.
    - Compute fraction within current stage (0..1).
    - Report VT power as: previous_stage_power + fraction * step_power

    Example: in the 175 W stage (previous 150 W), halfway through stage -> 150 + 0.5*25 = 162.5 W
    """
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

st.caption("Interpolation: innerhalb der aktuellen 3-min Stufe wird zwischen **vorheriger** und **aktueller** Stufe linear interpoliert (physiologischer Lag-Konvention).")

# Export stage table
csv_bytes = stage_tbl.to_csv(index=False).encode("utf-8")
st.download_button("Stufentabelle (letzte Sekunden) als CSV herunterladen", data=csv_bytes, file_name="stufen_last_window.csv", mime="text/csv")
