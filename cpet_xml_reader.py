# cpet_xml_reader.py
"""Read MetasoftStudio CPET exports saved as Excel 2003 XML (SpreadsheetML)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List, Tuple, Optional

import pandas as pd

NS = {
    "ss": "urn:schemas-microsoft-com:office:spreadsheet",
    "o": "urn:schemas-microsoft-com:office:office",
    "x": "urn:schemas-microsoft-com:office:excel",
    "html": "http://www.w3.org/TR/REC-html40",
}

def _row_to_values(row: ET.Element) -> List[Optional[str]]:
    vals: List[Optional[str]] = []
    idx = 0
    for cell in row.findall("ss:Cell", NS):
        ind = cell.get(f"{{{NS['ss']}}}Index")
        if ind is not None:
            ind0 = int(ind) - 1
            while idx < ind0:
                vals.append(None)
                idx += 1
        data = cell.find("ss:Data", NS)
        vals.append(data.text if data is not None else None)
        idx += 1
    return vals

def _find_timeseries_header(rows: List[ET.Element]) -> Tuple[int, List[str]]:
    for i, r in enumerate(rows):
        vals = _row_to_values(r)
        if not vals:
            continue
        first = (vals[0] or "").strip()
        joined = "|".join([v for v in vals if v])
        if first == "t" and ("V'O2" in joined or "VO2" in joined) and ("RER" in joined):
            header = [(v or "").strip() for v in vals]
            return i, header
    raise ValueError("Could not locate the time-series header row (starting with 't').")

def read_metasoftstudio_xml(xml_bytes: bytes) -> pd.DataFrame:
    root = ET.fromstring(xml_bytes)
    ws = root.find("ss:Worksheet", NS)
    if ws is None:
        raise ValueError("No Worksheet found in XML.")
    table = ws.find("ss:Table", NS)
    if table is None:
        raise ValueError("No Table found in Worksheet.")

    rows = table.findall("ss:Row", NS)
    header_idx, header = _find_timeseries_header(rows)

    data_start = header_idx + 2  # skip units row
    last_nonempty = 0
    for j, h in enumerate(header):
        if (h or "").strip() != "":
            last_nonempty = j
    ncols = last_nonempty + 1
    header = [h.strip() for h in header[:ncols]]

    data: List[List[Optional[str]]] = []
    for r in rows[data_start:]:
        vals = _row_to_values(r)
        if not vals:
            continue
        if len(vals) < ncols:
            vals = vals + [None] * (ncols - len(vals))
        vals = vals[:ncols]
        if vals[0] is None or str(vals[0]).strip() == "":
            break
        data.append(vals)

    if not data:
        raise ValueError("No time-series data rows found after header.")

    df = pd.DataFrame(data, columns=header)
    df.columns = [c.strip() for c in df.columns]
    return df
