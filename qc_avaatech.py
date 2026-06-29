"""
LAM+ Core QC — qc_avaatech.py
Streamlit Frontend for Avaatech XRF Core Scanner QC

Igor Oliveira, Andre Belem, F.R.I.D.A.Y. / LAM+

Uso:
    streamlit run qc_avaatech.py
"""

import io
import os
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from qc_core import (
    CORE_DEPTH_COL,
    DEPTH_COL,
    QF_INDETERMINATE,
    QF_PLOT_ORDER,
    add_pointwise_flag_notes,
    check_file,
    run_qc,
)
from i18n import TEXTS, DEFAULT_LANG

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PNG = os.path.join(BASE_DIR, "assets", "lamplus_logo.png")

QF_COLORS = {0: "#2ca02c", 1: "#ff7f0e", 2: "#d62728", 3: "#7f0000", QF_INDETERMINATE: "#7f7f7f"}

# ============================================================
# FIGURAS
# ============================================================

def plot_throughput(rep0, T, depth_col=DEPTH_COL):
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(rep0[depth_col], rep0["Throughput"], color="#2c7bb6", lw=0.8)
    ax.axhline(rep0["Throughput"].median(), color="gray", ls="--", lw=0.7, label=T["plot_throughput_median"])
    ax.set_xlabel(T["depth_axis"])
    ax.set_ylabel("Throughput")
    ax.set_title(T["plot_throughput_title"])
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def plot_rh(rep0, T, depth_col=DEPTH_COL):
    fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    for ax, col, title in zip(
        axes,
        ["Rh-La Area", "Rh-La-Inc Area"],
        [T["plot_rh1_title"], T["plot_rh2_title"]],
    ):
        ax.plot(rep0[depth_col], rep0[col], lw=0.8)
        ax.set_ylabel(col)
        ax.set_title(title)
    axes[-1].set_xlabel(T["depth_axis"])
    fig.tight_layout()
    return fig


def plot_rolling(rep0, T, depth_col=DEPTH_COL):
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(rep0[depth_col], rep0["Rh-La-Inc Area"], lw=0.8, label=T["plot_rolling_original"])
    ax.plot(rep0[depth_col], rep0["Rh-La-Inc Area_rolling"], lw=1.2, ls="--", label=T["plot_rolling_mean"])
    ax.set_xlabel(T["depth_axis"])
    ax.set_ylabel("Rh-La-Inc Area")
    ax.set_title(T["plot_rolling_title"])
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def plot_pca(rep0, p95, p99, T):
    fig, ax = plt.subplots(figsize=(6, 5))
    sc = ax.scatter(rep0["PC1"], rep0["PC2"], c=rep0["Mahalanobis"], cmap="RdYlGn_r", s=15, alpha=0.7)
    plt.colorbar(sc, ax=ax, label=T["plot_pca_colorbar"])
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_title(T["plot_pca_title"])
    fig.tight_layout()
    return fig


def plot_qi(rep0, T, depth_col=DEPTH_COL):
    c = rep0["QF"].map(QF_COLORS).fillna("#aaaaaa")
    qf_plot_pos = rep0["QF"].map(QF_PLOT_ORDER)
    fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    axes[0].bar(rep0[depth_col], rep0["QI"].fillna(0), color=c.values, width=8)
    axes[0].axhline(80, color="gray", ls="--", lw=0.7)
    axes[0].axhline(40, color="red", ls="--", lw=0.7)
    axes[0].set_ylabel(T["plot_qi_ylabel"])
    axes[0].set_title(T["plot_qi_title"])
    axes[1].bar(rep0[depth_col], qf_plot_pos, color=c.values, width=8)
    axes[1].set_yticks(list(QF_PLOT_ORDER.values()))
    axes[1].set_yticklabels(T["plot_qf_labels"])
    axes[1].set_xlabel(T["depth_axis"])
    axes[1].set_ylabel(T["plot_qf_ylabel"])
    fig.tight_layout()
    return fig


def plot_replicas(rep0, T, depth_col=DEPTH_COL):
    fig, ax = plt.subplots(figsize=(10, 3))
    valid = rep0.dropna(subset=["Mean_RPD"])
    ax.bar(valid[depth_col], valid["Mean_RPD"], width=8, color="#9467bd", alpha=0.8)
    ax.set_xlabel(T["depth_axis"])
    ax.set_ylabel(T["plot_replicas_ylabel"])
    ax.set_title(T["plot_replicas_title"])
    fig.tight_layout()
    return fig


# ============================================================
# EXPORT
# ============================================================

def to_excel_bytes(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="LAM_CoreQC")
    return buf.getvalue()


# ============================================================
# INTERFACE
# ============================================================

st.set_page_config(
    page_title=TEXTS[DEFAULT_LANG]["page_title"],
    page_icon=None,
    layout="wide",
)

LANG_OPTIONS = {"Português": "pt", "English": "en"}
lang_label = st.sidebar.selectbox(
    TEXTS[DEFAULT_LANG]["language_label"] + " / Language",
    options=list(LANG_OPTIONS.keys()),
    index=0,
)
lang = LANG_OPTIONS[lang_label]
T = TEXTS[lang]

DEPTH_DISPLAY_OPTIONS = {
    T["depth_display_composite"]: DEPTH_COL,
    T["depth_display_core"]: CORE_DEPTH_COL,
}
depth_display_label = st.sidebar.selectbox(
    T["depth_display_label"],
    options=list(DEPTH_DISPLAY_OPTIONS.keys()),
    index=0,
    help=T["depth_display_help"],
)
DEPTH_DISPLAY_COL = DEPTH_DISPLAY_OPTIONS[depth_display_label]

strict_missing_data = st.sidebar.checkbox(
    T["strict_missing_label"],
    value=True,
    help=T["strict_missing_help"],
)
combine_rolling_vars = st.sidebar.checkbox(
    T["combine_rolling_label"],
    value=False,
    help=T["combine_rolling_help"],
)

col_title, col_logo = st.columns([5, 1])
with col_title:
    st.title(T["app_title"])
    st.caption(T["app_caption"])
with col_logo:
    if os.path.isfile(LOGO_PNG):
        st.image(LOGO_PNG, width=100)

uploaded = st.file_uploader(T["upload_label"], type=["xlsx"])

if uploaded is None:
    st.info(T["upload_info"])
    st.stop()

# Leitura
try:
    df_raw = pd.read_excel(uploaded)
except Exception as e:
    st.error(T["read_error"].format(error=e))
    st.stop()

st.success(T["load_success"].format(rows=df_raw.shape[0], cols=df_raw.shape[1]))

# Check de consistência
errors, warnings = check_file(df_raw, lang=lang)

if errors:
    for e in errors:
        st.error(T["error_prefix"].format(msg=e))
    st.stop()

if warnings:
    for w in warnings:
        st.warning(T["warning_prefix"].format(msg=w))

# Rodar QC
with st.spinner(T["qc_spinner"]):
    try:
        rep0, p95, p99, pca_elements = run_qc(
            df_raw, strict_missing_data=strict_missing_data, combine_rolling_vars=combine_rolling_vars
        )
        rep0 = add_pointwise_flag_notes(rep0, lang=lang)
    except Exception as e:
        st.error(T["qc_error"].format(error=e))
        st.stop()

# Resumo
st.subheader(T["summary_header"])
col1, col2, col3, col4, col5 = st.columns(5)
qf_counts = rep0["QF"].value_counts().sort_index()
col1.metric(T["metric_measurements"], len(rep0))
col2.metric(T["metric_mean_qi"], f"{rep0['QI'].mean():.1f}")
col3.metric(T["metric_qf_ok"], qf_counts.get(0, 0))
col4.metric(T["metric_qf_rejected"], qf_counts.get(3, 0))
col5.metric(T["metric_qf_indeterminate"], qf_counts.get(QF_INDETERMINATE, 0))

# Figuras
st.subheader(T["diagnostics_header"])

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    T["tab_throughput"], T["tab_rh"], T["tab_rolling"],
    T["tab_replicas"], T["tab_pca"], T["tab_qi"],
])

with tab1:
    st.pyplot(plot_throughput(rep0, T, depth_col=DEPTH_DISPLAY_COL))

with tab2:
    st.pyplot(plot_rh(rep0, T, depth_col=DEPTH_DISPLAY_COL))

with tab3:
    st.pyplot(plot_rolling(rep0, T, depth_col=DEPTH_DISPLAY_COL))

with tab4:
    st.pyplot(plot_replicas(rep0, T, depth_col=DEPTH_DISPLAY_COL))

with tab5:
    if rep0["Mahalanobis"].notna().any():
        st.pyplot(plot_pca(rep0, p95, p99, T))
    else:
        st.info(T["pca_skipped_info"])

with tab6:
    st.pyplot(plot_qi(rep0, T, depth_col=DEPTH_DISPLAY_COL))

# Tabela
st.subheader(T["data_header"])
display_cols = [DEPTH_DISPLAY_COL] + [c for c in rep0.columns if c != DEPTH_DISPLAY_COL]
st.dataframe(rep0[display_cols], use_container_width=True)

# Download
st.download_button(
    label=T["download_label"],
    data=to_excel_bytes(rep0),
    file_name="LAM_CoreQC_Output.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
