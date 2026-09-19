import pandas as pd
import streamlit as st

from cleaner import clean_dataframe
from dashboard import build_charts, column_groups, kpis
from exporters import powerbi_m_script, to_csv_bytes, to_excel_bytes

st.set_page_config(page_title="Excel Cleaner & Dashboard", page_icon="📊", layout="wide")
st.title("📊 Excel Cleaner & Dashboard")
st.caption("Upload a messy Excel file → get clean data, an instant dashboard, and Power BI-ready downloads.")

up = st.sidebar.file_uploader("Upload Excel / CSV", type=["xlsx", "xls", "csv"])
drop_dupes = st.sidebar.checkbox("Remove duplicate rows", True)
flag_out = st.sidebar.checkbox("Flag outliers (IQR)", True)

if not up:
    st.info("Upload a file in the sidebar to begin.")
    st.stop()


@st.cache_data(show_spinner=False)
def load(file_bytes: bytes, name: str, sheet):
    import io
    if name.lower().endswith(".csv"):
        return pd.read_csv(io.BytesIO(file_bytes), dtype=object)
    return pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, dtype=object)


raw_bytes = up.getvalue()
sheet = 0
if not up.name.lower().endswith(".csv"):
    sheets = pd.ExcelFile(__import__("io").BytesIO(raw_bytes)).sheet_names
    sheet = st.sidebar.selectbox("Sheet", sheets) if len(sheets) > 1 else sheets[0]

raw = load(raw_bytes, up.name, sheet)
clean, log = clean_dataframe(raw, drop_dupes=drop_dupes, flag_outliers=flag_out)

tab1, tab2, tab3 = st.tabs(["🧹 Cleaning", "📈 Dashboard", "⬇️ Downloads"])

with tab1:
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows", f"{len(clean):,}", f"{len(clean) - len(raw):,} vs raw")
    c2.metric("Columns", clean.shape[1], f"{clean.shape[1] - raw.shape[1]} vs raw")
    c3.metric("Missing cells", int(clean.isna().sum().sum()), f"{int(clean.isna().sum().sum() - raw.isna().sum().sum())} vs raw")
    st.subheader("Cleaning log")
    st.dataframe(pd.DataFrame(log), use_container_width=True, hide_index=True)
    a, b = st.columns(2)
    a.subheader("Before"); a.dataframe(raw.head(50), use_container_width=True)
    b.subheader("After"); b.dataframe(clean.head(50), use_container_width=True)

with tab2:
    nums, cats, dates = column_groups(clean)
    view = clean
    with st.expander("Filters", expanded=False):
        for c in cats[:4]:
            picked = st.multiselect(c, sorted(clean[c].astype(str).unique()), key=f"f_{c}")
            if picked:
                view = view[view[c].astype(str).isin(picked)]
    cols = st.columns(min(len(kpis(view, nums)), 6))
    for col, (label, val) in zip(cols, kpis(view, nums)):
        col.metric(label, val)
    charts = build_charts(view)
    for i in range(0, len(charts), 2):
        row = st.columns(2)
        for slot, (title, fig) in zip(row, charts[i:i + 2]):
            slot.markdown(f"**{title}**")
            slot.plotly_chart(fig, use_container_width=True)

with tab3:
    st.write("Continue in Power BI: download the workbook, then paste the script into Power Query.")
    d1, d2, d3 = st.columns(3)
    d1.download_button("Cleaned Excel (+ log sheet)", to_excel_bytes(clean, log), "cleaned_data.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    d2.download_button("Cleaned CSV", to_csv_bytes(clean), "cleaned_data.csv", "text/csv")
    d3.download_button("Power BI script (.pq)", powerbi_m_script(clean), "load_cleaned_data.pq", "text/plain")