"""Generic Excel/DataFrame cleaning with a human-readable log."""
import re
import warnings

import numpy as np
import pandas as pd

NULL_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-", "--", "?", "#n/a", "nil"}


def _snake(name) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip()).strip("_").lower()
    return s or "column"


def _dedupe(names):
    seen, out = {}, []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 0
            out.append(n)
    return out


def _to_numeric(series: pd.Series):
    txt = series.astype("string").str.strip()
    txt = txt.str.replace(r"[,\s$€£₹]", "", regex=True).str.replace("%", "", regex=False)
    txt = txt.str.replace(r"^\((.*)\)$", r"-\1", regex=True)  # (123) -> -123
    return pd.to_numeric(txt, errors="coerce")


def _to_datetime(series: pd.Series):
    """Try month-first and day-first parsing; keep whichever parses more values."""
    txt = series.astype("string")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        a = pd.to_datetime(txt, errors="coerce", dayfirst=False)
        b = pd.to_datetime(txt, errors="coerce", dayfirst=True)
    return b if b.notna().sum() > a.notna().sum() else a


def clean_dataframe(df: pd.DataFrame, drop_dupes=True, flag_outliers=True):
    """Return (clean_df, log) where log is a list of {step, detail} dicts."""
    log = []

    def add(step, detail):
        log.append({"step": step, "detail": detail})

    df = df.copy()

    # 1. Drop fully empty rows / columns
    n_r, n_c = len(df), df.shape[1]
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if len(df) < n_r:
        add("Empty rows", f"Removed {n_r - len(df)} fully empty rows")
    if df.shape[1] < n_c:
        add("Empty columns", f"Removed {n_c - df.shape[1]} fully empty columns")

    # 2. Normalise column names
    old = list(df.columns)
    new = _dedupe([_snake(c) for c in old])
    changed = [(o, n) for o, n in zip(old, new) if str(o) != n]
    df.columns = new
    if changed:
        add("Column names", f"Standardised {len(changed)} names (e.g. '{changed[0][0]}' -> '{changed[0][1]}')")

    # 3. Trim whitespace + convert null-like tokens
    for col in df.columns:
        if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            s = df[col].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
            mask = s.str.lower().isin(NULL_TOKENS)
            if mask.sum():
                add("Null tokens", f"'{col}': {int(mask.sum())} placeholder values (N/A, -, etc.) set to missing")
            df[col] = s.mask(mask)

    # 3b. Unify inconsistent casing in text columns ("north" vs "North")
    for col in df.columns:
        s = df[col]
        if not (s.dtype == object or pd.api.types.is_string_dtype(s)):
            continue
        non_null = s.dropna()
        if non_null.empty or non_null.nunique() > 200:
            continue
        lower = non_null.str.lower()
        if lower.nunique() < non_null.nunique():
            canon = non_null.groupby(lower).agg(lambda x: x.value_counts().idxmax())
            df[col] = s.where(s.isna(), s.str.lower().map(canon))
            add("Text casing", f"'{col}': merged {non_null.nunique() - lower.nunique()} case variants")

    # 4. Type inference
    for col in df.columns:
        s = df[col]
        if not (s.dtype == object or pd.api.types.is_string_dtype(s)):
            continue
        non_null = s.dropna()
        if non_null.empty:
            continue
        num = _to_numeric(s)
        if num.notna().sum() / len(non_null) >= 0.9:
            df[col] = num
            add("Data types", f"'{col}' converted to numeric")
            continue
        looks_dateish = non_null.astype(str).str.contains(r"[-/:]|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", case=False, regex=True).mean() > 0.8
        if looks_dateish:
            dt = _to_datetime(s)
            if dt.notna().sum() / len(non_null) >= 0.9:
                df[col] = dt
                add("Data types", f"'{col}' converted to date/time")
                continue
        if non_null.nunique() / len(non_null) < 0.5:
            df[col] = s.astype("category")

    # 5. Duplicates
    if drop_dupes:
        n = len(df)
        df = df.drop_duplicates()
        if len(df) < n:
            add("Duplicates", f"Removed {n - len(df)} duplicate rows")

    # 6. Missing values
    for col in df.columns:
        n_miss = int(df[col].isna().sum())
        if not n_miss:
            continue
        pct = n_miss / len(df) * 100
        if pd.api.types.is_numeric_dtype(df[col]):
            med = df[col].median()
            df[col] = df[col].fillna(med)
            add("Missing values", f"'{col}': {n_miss} ({pct:.1f}%) filled with median ({med:.4g})")
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            add("Missing values", f"'{col}': {n_miss} ({pct:.1f}%) missing dates left blank")
        else:
            if isinstance(df[col].dtype, pd.CategoricalDtype):
                df[col] = df[col].cat.add_categories("Unknown")
            df[col] = df[col].fillna("Unknown")
            add("Missing values", f"'{col}': {n_miss} ({pct:.1f}%) filled with 'Unknown'")

    # 7. Outliers (flag, never delete)
    if flag_outliers:
        flag = pd.Series(False, index=df.index)
        for col in df.select_dtypes(include=np.number).columns:
            if df[col].nunique() < 10:
                continue
            q1, q3 = df[col].quantile([0.25, 0.75])
            iqr = q3 - q1
            if iqr == 0:
                continue
            m = (df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)
            if m.sum():
                add("Outliers", f"'{col}': {int(m.sum())} values outside 1.5xIQR (flagged, not removed)")
                flag |= m
        if flag.any():
            df["has_outlier"] = flag

    df = df.reset_index(drop=True)
    if not log:
        add("Result", "Data was already clean - no changes needed")
    return df, log