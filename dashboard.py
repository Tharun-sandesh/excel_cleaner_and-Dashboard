"""Auto-generate KPIs and Plotly charts from any cleaned DataFrame."""
import pandas as pd
import plotly.express as px


def column_groups(df: pd.DataFrame):
    skip = {"has_outlier"}
    nums = [c for c in df.select_dtypes("number").columns if c not in skip]
    dates = list(df.select_dtypes(include=["datetime", "datetimetz"]).columns)
    cats = [c for c in df.columns if c not in nums + dates + list(skip)
            and 1 < df[c].nunique() <= 30]
    return nums, cats, dates


def kpis(df: pd.DataFrame, nums):
    out = [("Rows", f"{len(df):,}"), ("Columns", f"{df.shape[1]:,}")]
    for c in nums[:2]:
        out.append((f"Total {c}", f"{df[c].sum():,.2f}"))
        out.append((f"Avg {c}", f"{df[c].mean():,.2f}"))
    return out


def build_charts(df: pd.DataFrame, max_per_type=4):
    nums, cats, dates = column_groups(df)
    charts = []

    for c in nums[:max_per_type]:
        charts.append((f"Distribution of {c}", px.histogram(df, x=c, nbins=30)))

    for c in cats[:max_per_type]:
        counts = df[c].astype(str).value_counts().head(15).reset_index()
        counts.columns = [c, "count"]
        charts.append((f"Count by {c}", px.bar(counts, x=c, y="count")))
        if nums:
            agg = df.groupby(c, observed=True)[nums[0]].sum().nlargest(15).reset_index()
            charts.append((f"{nums[0]} by {c}", px.bar(agg, x=c, y=nums[0])))

    if dates and nums:
        d = dates[0]
        ts = df.set_index(d)[nums[:3]].resample("MS").sum().reset_index()
        charts.append((f"Monthly trend ({d})", px.line(ts, x=d, y=nums[:3], markers=True)))

    if len(nums) >= 2:
        corr = df[nums].corr().round(2)
        charts.append(("Correlation heatmap",
                       px.imshow(corr, text_auto=True, color_continuous_scale="RdBu_r", zmin=-1, zmax=1)))

    for _, fig in charts:
        fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), height=340)
    return charts