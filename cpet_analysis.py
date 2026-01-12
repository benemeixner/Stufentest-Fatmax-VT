# cpet_analysis.py
"""Stage alignment, last-window stage means, FatOx calculations."""

from __future__ import annotations

from typing import Tuple
import numpy as np
import pandas as pd


def parse_time_to_seconds(t: pd.Series) -> np.ndarray:
    s = t.astype(str).str.strip().str.replace(",", ".", regex=False)

    def one(x: str) -> float:
        if not x or x.lower() in {"nan", "none"}:
            return np.nan
        parts = x.split(":")
        try:
            if len(parts) == 3:
                h, m, sec = parts
                return float(h) * 3600 + float(m) * 60 + float(sec)
            if len(parts) == 2:
                m, sec = parts
                return float(m) * 60 + float(sec)
            return float(x)
        except Exception:
            return np.nan

    out = np.array([one(v) for v in s.to_list()], dtype=float)
    if np.isfinite(out).mean() < 0.95:
        raise ValueError("Time column could not be parsed reliably.")
    return out


def assign_stages(
    df: pd.DataFrame,
    offset_s: float,
    stage_duration_s: float = 180.0,
    start_power_w: float = 75.0,
    step_power_w: float = 25.0,
) -> pd.DataFrame:
    out = df.copy()
    t_s = parse_time_to_seconds(out["t"])
    out["t_s"] = t_s

    stage_idx = np.floor((t_s - float(offset_s)) / float(stage_duration_s)).astype(int)
    stage_idx[(t_s < float(offset_s))] = -1
    out["stage_idx"] = stage_idx
    out["stage_power_w"] = np.where(stage_idx >= 0, start_power_w + step_power_w * stage_idx, np.nan)
    return out


def stage_lastwindow_means(
    df: pd.DataFrame,
    stage_duration_s: float = 180.0,
    last_window_s: float = 30.0,
) -> pd.DataFrame:
    if "t_s" not in df.columns or "stage_idx" not in df.columns:
        raise ValueError("df must include t_s and stage_idx (use assign_stages first).")

    out_rows = []
    for sid in sorted(df.loc[df["stage_idx"] >= 0, "stage_idx"].unique()):
        sub = df[df["stage_idx"] == sid].copy()
        if sub.empty:
            continue
        t0 = float(sub["t_s"].min())
        stage_end = t0 + float(stage_duration_s)
        win_start = stage_end - float(last_window_s)
        win = sub[(sub["t_s"] >= win_start) & (sub["t_s"] <= stage_end)]
        if win.empty:
            t1 = float(sub["t_s"].max())
            win = sub[sub["t_s"] >= (t1 - float(last_window_s))]

        row = {
            "stage_idx": int(sid),
            "stage_power_w": float(sub["stage_power_w"].iloc[0]) if "stage_power_w" in sub.columns else np.nan,
            "t_start_s": t0,
            "t_end_s": stage_end,
            "n_samples": int(win.shape[0]),
        }
        for col in ["V'O2", "V'CO2", "V'E", "RER", "V'E/V'O2", "V'E/V'CO2", "VT", "AF", "HF",
                    "PETO2", "PETCO2", "EQO2", "EQCO2"]:
            if col in win.columns:
                row[col] = float(pd.to_numeric(win[col], errors="coerce").mean())
        out_rows.append(row)

    return pd.DataFrame(out_rows)


def frayn_fat_cho_oxidation(vo2_l_min: float, vco2_l_min: float) -> Tuple[float, float]:
    vo2 = float(vo2_l_min)
    vco2 = float(vco2_l_min)
    fat = 1.695 * vo2 - 1.701 * vco2
    cho = 4.585 * vco2 - 3.226 * vo2
    return fat, cho


def add_fatox_table(stage_tbl: pd.DataFrame) -> pd.DataFrame:
    out = stage_tbl.copy()
    if "V'O2" in out.columns and "V'CO2" in out.columns:
        fats, chos = [], []
        for vo2, vco2 in zip(out["V'O2"], out["V'CO2"]):
            if pd.isna(vo2) or pd.isna(vco2):
                fats.append(np.nan); chos.append(np.nan)
            else:
                f, c = frayn_fat_cho_oxidation(vo2, vco2)
                fats.append(f); chos.append(c)
        out["FatOx_g_min"] = fats
        out["CHOox_g_min"] = chos
    return out
