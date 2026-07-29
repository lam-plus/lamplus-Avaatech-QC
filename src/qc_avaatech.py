"""
LAM+ Core QC V2 — qc_avaatech.py

Interface mínima em Streamlit: upload, validação, processamento,
visualização de resumo e download. Único ponto de entrada da UI da V2.

Não contém cálculo científico (delega a qc_core.py/qc_io.py/qc_reports.py)
e não importa nada de LEGACY/. Sem PCA, sem múltiplos modos de QF, sem
opções avançadas (ver DEVELOPMENT.md, seção 8).

Uso:
    streamlit run src/qc_avaatech.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from qc_core import run_qc
from qc_io import check_columns, read_workbook
from qc_reports import build_excel_report, build_summary, format_summary_text


def _validate_sheets(sheets: list[dict]) -> list[dict]:
    """
    Roda check_columns em cada aba lida e exibe erros/avisos antes de
    qualquer processamento.

    Contrato:
        - Erros bloqueiam a aba (não entra no retorno) -- avisos aparecem
          mas não impedem a aba de ser processada.
        - Não modifica `sheets`.
    """
    valid_sheets = []
    for sheet in sheets:
        sheet_name, energy, df_raw = sheet["sheet_name"], sheet["energy"], sheet["df"]
        errors, warnings = check_columns(df_raw, energy)
        for error in errors:
            st.error(f"[{sheet_name}] {error}")
        for warning in warnings:
            st.warning(f"[{sheet_name}] {warning}")
        if not errors:
            valid_sheets.append(sheet)
    return valid_sheets


def _run_pipeline(sheets: list[dict]) -> list[dict]:
    """Roda qc_core.run_qc em cada aba já validada por _validate_sheets."""
    sheet_results = []
    for sheet in sheets:
        rep0 = run_qc(sheet["df"], sheet["energy"])
        sheet_results.append(
            {
                "sheet_name": sheet["sheet_name"],
                "energy": sheet["energy"],
                "rep0": rep0,
                "df_raw": sheet["df"],
            }
        )
    return sheet_results


def main() -> None:
    """Ponto de entrada da UI."""
    st.set_page_config(page_title="LAM+ Core QC", layout="wide")
    st.title("LAM+ Core QC")
    st.caption("V2 — controle de qualidade da aquisição Avaatech XRF Core Scanner.")

    uploaded = st.file_uploader("Workbook Avaatech (.xlsx)", type=["xlsx"])
    if uploaded is None:
        st.info("Faça upload de um workbook .xlsx exportado pelo Avaatech.")
        return

    try:
        sheets, skipped = read_workbook(uploaded)
    except Exception as exc:
        st.error(f"Erro ao ler o workbook: {exc}")
        return

    if not sheets:
        st.error("Nenhuma aba com energia reconhecível (10kV/30kV/50kV) foi encontrada.")
        return

    st.caption(
        "Abas encontradas: "
        + ", ".join(f"{s['sheet_name']} ({s['energy']})" for s in sheets)
    )
    if skipped:
        st.warning("Abas ignoradas (energia não reconhecida pelo nome): " + ", ".join(skipped))

    st.subheader("Validação")
    valid_sheets = _validate_sheets(sheets)
    if not valid_sheets:
        st.error("Nenhuma aba passou na validação. Corrija os erros acima e reenvie o arquivo.")
        return

    if st.button("Executar QC"):
        st.session_state["sheet_results"] = _run_pipeline(valid_sheets)
        st.session_state["file_name"] = uploaded.name

    sheet_results = st.session_state.get("sheet_results")
    file_name = st.session_state.get("file_name")
    if not sheet_results or file_name != uploaded.name:
        return

    st.subheader("Resumo")
    summary = build_summary(sheet_results, file_name=file_name)
    for energy, stats in summary["energies"].items():
        st.markdown(f"**{energy}**")
        qf = stats["qf_distribution"]
        cols = st.columns(6)
        cols[0].metric("n(Rep0)", stats["n_measurements"])
        cols[1].metric("QF0", qf["QF0"])
        cols[2].metric("QF1", qf["QF1"])
        cols[3].metric("QF2", qf["QF2"])
        cols[4].metric("QF3", qf["QF3"])
        cols[5].metric("INDETERMINATE", qf["INDETERMINATE"])

    st.subheader("Resultados QC")
    for result in sheet_results:
        st.caption(f"{result['sheet_name']} ({result['energy']})")
        st.dataframe(result["rep0"], use_container_width=True)

    st.subheader("Download")
    stem = Path(file_name).stem
    st.download_button(
        "Baixar Excel (.xlsx)",
        data=build_excel_report(sheet_results),
        file_name=f"{stem}_QC.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        "Baixar resumo (.txt)",
        data=format_summary_text(summary),
        file_name=f"{stem}_resumo.txt",
        mime="text/plain",
    )


if __name__ == "__main__":
    main()
