# Stufentest-App v2: FatMax Punkte vs Leistung + VT-Leistung interpoliert

Neu:
- FatMax als **Scatter (FatOx vs Leistung)**, Auswahl über Leistungs-Slider (visuell auf Punkte schauen → auswählen)
- VT1/VT2 als **interpolierte Leistung** innerhalb einer Stufe:
  VT_P = previous_stage_power + fraction_in_stage * step_power

Deploy main file: `app_cpet_step.py`
