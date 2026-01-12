# Stufentest-App v7

Fixes:
- FatMax Scatter wird jetzt mit `st.plotly_chart(..., on_select="rerun", selection_mode=("points",))` gerendert (kein streamlit-plotly-events).
  → Dadurch verschwindet der Plot nicht mehr auf Streamlit Cloud.
- x-Achse wird explizit numerisch erzwungen (falls irgendwo Komma-Dezimalwerte auftauchen).
- y-Achse für FatOx ist fixiert (`fixedrange=True`), damit Zoom/Pan auf x die y-Skala nicht „sprengt“.

Wasserman:
- 1 Hz Aggregation + 30 s rolling mean (centered) für Zeitreihen-Panels.

Deploy main file: `app_cpet_step.py`
