"""
LAM+ Core QC — qc_avaatech.py
Streamlit Frontend for Avaatech XRF Core Scanner QC

Igor Oliveira / LAM+

Uso:
    streamlit run qc_avaatech.py
"""

import io
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from qc_core import (
    DEPTH_COL,
    check_file,
    run_qc,
)

# ============================================================
# FIGURAS
# ============================================================

def plot_throughput(rep0):
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(rep0[DEPTH_COL], rep0["Throughput"], color="#2c7bb6", lw=0.8)
    ax.axhline(rep0["Throughput"].median(), color="gray", ls="--", lw=0.7, label="mediana")
    ax.set_xlabel("Profundidade (mm)")
    ax.set_ylabel("Throughput")
    ax.set_title("QC1 — Throughput")
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def plot_rh(rep0):
    fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    for ax, col, title in zip(
        axes,
        ["Rh-La Area", "Rh-La-Inc Area"],
        ["QC2 — Rh-Lα", "QC3 — Rh-Lα-Inc"],
    ):
        ax.plot(rep0[DEPTH_COL], rep0[col], lw=0.8)
        ax.set_ylabel(col)
        ax.set_title(title)
    axes[-1].set_xlabel("Profundidade (mm)")
    fig.tight_layout()
    return fig


def plot_rolling(rep0):
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(rep0[DEPTH_COL], rep0["Rh-La-Inc Area"], lw=0.8, label="original")
    ax.plot(rep0[DEPTH_COL], rep0["Rh-La-Inc Area_rolling"], lw=1.2, ls="--", label="rolling mean")
    ax.set_xlabel("Profundidade (mm)")
    ax.set_ylabel("Rh-La-Inc Area")
    ax.set_title("QC4 — Rolling QC (Rh-Lα-Inc)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def plot_pca(rep0, p95, p99):
    fig, ax = plt.subplots(figsize=(6, 5))
    sc = ax.scatter(rep0["PC1"], rep0["PC2"], c=rep0["Mahalanobis"], cmap="RdYlGn_r", s=15, alpha=0.7)
    plt.colorbar(sc, ax=ax, label="Distância Mahalanobis")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_title("QC6 — PCA (colorido por Mahalanobis)")
    fig.tight_layout()
    return fig


def plot_qi(rep0):
    colors = {0: "#2ca02c", 1: "#ff7f0e", 2: "#d62728", 3: "#7f0000"}
    c = rep0["QF"].map(colors).fillna("#aaaaaa")
    fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    axes[0].bar(rep0[DEPTH_COL], rep0["QI"], color=c.values, width=8)
    axes[0].axhline(80, color="gray", ls="--", lw=0.7)
    axes[0].axhline(40, color="red", ls="--", lw=0.7)
    axes[0].set_ylabel("Quality Index")
    axes[0].set_title("Quality Index (QI) e Quality Flag (QF)")
    axes[1].bar(rep0[DEPTH_COL], rep0["QF"], color=c.values, width=8)
    axes[1].set_yticks([0, 1, 2, 3])
    axes[1].set_yticklabels(["0-OK", "1-Atenção", "2-Suspeito", "3-Rejeitado"])
    axes[1].set_xlabel("Profundidade (mm)")
    axes[1].set_ylabel("Quality Flag")
    fig.tight_layout()
    return fig


def plot_replicas(rep0):
    fig, ax = plt.subplots(figsize=(10, 3))
    valid = rep0.dropna(subset=["Mean_RPD"])
    ax.bar(valid[DEPTH_COL], valid["Mean_RPD"], width=8, color="#9467bd", alpha=0.8)
    ax.set_xlabel("Profundidade (mm)")
    ax.set_ylabel("RPD médio (%)")
    ax.set_title("QC5 — Réplicas (Mean RPD)")
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
    page_title="LAM+ Core QC",
    page_icon=None,
    layout="wide",
)

st.title("LAM+ Core QC v2.1")
st.caption("Quality Control Protocol for Avaatech XRF Core Scanner")

uploaded = st.file_uploader("Upload do arquivo Excel (.xlsx)", type=["xlsx"])

if uploaded is None:
    st.info("Faça o upload do arquivo de dados do Avaatech para iniciar o QC.")
    st.stop()

# Leitura
try:
    df_raw = pd.read_excel(uploaded)
except Exception as e:
    st.error(f"Erro ao ler o arquivo: {e}")
    st.stop()

st.success(f"Arquivo carregado: {df_raw.shape[0]} linhas, {df_raw.shape[1]} colunas.")

# Check de consistência
errors, warnings = check_file(df_raw)

if errors:
    for e in errors:
        st.error(f"ERRO: {e}")
    st.stop()

if warnings:
    for w in warnings:
        st.warning(f"AVISO: {w}")

# Rodar QC
with st.spinner("Executando pipeline QC..."):
    try:
        rep0, p95, p99, pca_elements = run_qc(df_raw)
    except Exception as e:
        st.error(f"Erro durante o QC: {e}")
        st.stop()

# Resumo
st.subheader("Resumo")
col1, col2, col3, col4 = st.columns(4)
qf_counts = rep0["QF"].value_counts().sort_index()
col1.metric("Medidas (Rep0)", len(rep0))
col2.metric("QI médio", f"{rep0['QI'].mean():.1f}")
col3.metric("QF=0 (OK)", qf_counts.get(0, 0))
col4.metric("QF=3 (Rejeitado)", qf_counts.get(3, 0))

# Figuras
st.subheader("Diagnósticos")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Throughput", "Rh-Lα / Rh-Lα-Inc", "Rolling QC", "Réplicas", "PCA", "QI / QF"
])

with tab1:
    st.pyplot(plot_throughput(rep0))

with tab2:
    st.pyplot(plot_rh(rep0))

with tab3:
    st.pyplot(plot_rolling(rep0))

with tab4:
    st.pyplot(plot_replicas(rep0))

with tab5:
    st.pyplot(plot_pca(rep0, p95, p99))

with tab6:
    st.pyplot(plot_qi(rep0))

# Tabela
st.subheader("Dados com QC")
st.dataframe(rep0, use_container_width=True)

# Download
st.download_button(
    label="Download resultado (.xlsx)",
    data=to_excel_bytes(rep0),
    file_name="LAM_CoreQC_Output.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
