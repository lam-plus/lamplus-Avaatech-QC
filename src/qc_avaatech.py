"""
LAM+ Core QC V2 — qc_avaatech.py

Interface mínima em Streamlit: upload, processamento, visualização de
resumo e download. Único ponto de entrada da UI da V2.

Não contém cálculo científico (delega a qc_core.py/qc_io.py/qc_reports.py)
e não importa nada de LEGACY/.

Uso:
    streamlit run src/qc_avaatech.py
"""

from __future__ import annotations

import streamlit as st

from qc_config import SUPPORTED_ENERGIES  # noqa: F401  (uso futuro: seletor de energia)

# qc_core / qc_io / qc_reports serão usados quando a lógica de
# processamento for implementada (Etapas 2-6) — sem lógica ainda.


def main() -> None:
    """Ponto de entrada da UI. Sem lógica de processamento nesta etapa."""
    st.set_page_config(page_title="LAM+ Core QC", layout="wide")
    st.title("LAM+ Core QC")
    st.caption("V2 — estrutura inicial, sem lógica de processamento.")

    st.file_uploader("Workbook Avaatech (.xlsx)", type=["xlsx"])


if __name__ == "__main__":
    main()
