"""Downloadable outputs: cleaned Excel (+ log sheet), CSV, and a Power BI Power Query script."""
import io

import pandas as pd


def to_excel_bytes(df: pd.DataFrame, log: list) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as xw:
        out = df.copy()
        for c in out.select_dtypes("category").columns:
            out[c] = out[c].astype(str)
        out.to_excel(xw, sheet_name="Cleaned Data", index=False)
        pd.DataFrame(log).to_excel(xw, sheet_name="Cleaning Log", index=False)
        ws = xw.sheets["Cleaned Data"]
        for i, col in enumerate(out.columns):
            width = min(max(len(str(col)), out[col].astype(str).str.len().max() or 0) + 2, 40)
            ws.set_column(i, i, width)
        ws.freeze_panes(1, 0)
    return buf.getvalue()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def powerbi_m_script(df: pd.DataFrame, filename="cleaned_data.xlsx") -> str:
    """Power Query (M) that loads the cleaned workbook with correct column types."""
    def m_type(s):
        if pd.api.types.is_bool_dtype(s):
            return "type logical"
        if pd.api.types.is_integer_dtype(s):
            return "Int64.Type"
        if pd.api.types.is_numeric_dtype(s):
            return "type number"
        if pd.api.types.is_datetime64_any_dtype(s):
            return "type datetime"
        return "type text"

    types = ",\n        ".join(f'{{"{c}", {m_type(df[c])}}}' for c in df.columns)
    return f'''// Power BI: Home > Get Data > Blank Query > Advanced Editor > paste this.
// Edit the path below to where you saved {filename}.
let
    Source   = Excel.Workbook(File.Contents("C:\\Users\\YOU\\Downloads\\{filename}"), null, true),
    Sheet    = Source{{[Item="Cleaned Data", Kind="Sheet"]}}[Data],
    Promoted = Table.PromoteHeaders(Sheet, [PromoteAllScalars=true]),
    Typed    = Table.TransformColumnTypes(Promoted, {{
        {types}
    }})
in
    Typed
'''