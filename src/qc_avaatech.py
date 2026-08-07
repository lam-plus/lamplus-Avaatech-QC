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

import time
from pathlib import Path

import pandas as pd
import streamlit as st

from qc_audit import query_runs, register_run
from qc_core import run_qc
from qc_io import check_columns, read_workbook
from qc_reports import build_excel_report, build_summary, format_summary_text

# Cores da barra de distribuição de QF (protocolo v4.2): verde=QF0,
# amarelo=QF1, laranja=QF2, vermelho=QF3, cinza=INDETERMINATE (neutro, não
# "grave"). Mesma paleta conceitual da coloração do Excel (qc_reports.py),
# mas com laranja adicional para distinguir QF2 de QF3 visualmente.
QF_BAR_COLORS = {
    "QF0": "#1baf7a",
    "QF1": "#eda100",
    "QF2": "#eb6834",
    "QF3": "#d03b3b",
    "INDETERMINATE": "#888780",
}

# Caminho absoluto (independente do cwd de onde `streamlit run` foi
# chamado) para o logo exibido no cabeçalho da interface.
LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "lamplus_logo.png"


def _validate_sheets(sheets: list[dict]) -> tuple[list[dict], dict[str, list[str]]]:
    """
    Roda check_columns em cada aba lida e exibe erros/avisos antes de
    qualquer processamento.

    Contrato:
        - Erros bloqueiam a aba (não entra em `valid_sheets`) -- avisos
          aparecem mas não impedem a aba de ser processada.
        - Não modifica `sheets`.

    Saída:
        valid_sheets: abas sem erro bloqueante.
        warnings_by_sheet: avisos de check_columns por sheet_name (de todas
            as abas, inclusive as bloqueadas por erro) -- usado só para
            registrar em auditoria (ver qc_audit.register_run), não afeta
            o processamento.
    """
    valid_sheets = []
    warnings_by_sheet: dict[str, list[str]] = {}
    for sheet in sheets:
        sheet_name, energy, df_raw = sheet["sheet_name"], sheet["energy"], sheet["df"]
        errors, warnings = check_columns(df_raw, energy)
        for error in errors:
            st.error(f"[{sheet_name}] {error}")
        for warning in warnings:
            st.warning(f"[{sheet_name}] {warning}")
        warnings_by_sheet[sheet_name] = warnings
        if not errors:
            valid_sheets.append(sheet)
    return valid_sheets, warnings_by_sheet


def _run_pipeline(
    sheets: list[dict], warnings_by_sheet: dict[str, list[str]] | None = None
) -> list[dict]:
    """
    Roda qc_core.run_qc em cada aba já validada por _validate_sheets.

    `warnings_by_sheet` (saída de _validate_sheets) é anexado a cada
    resultado como "warnings", só para ser registrado em auditoria (ver
    qc_audit.register_run) -- não influencia o cálculo.
    """
    warnings_by_sheet = warnings_by_sheet or {}
    sheet_results = []
    for sheet in sheets:
        rep0 = run_qc(sheet["df"], sheet["energy"])
        sheet_results.append(
            {
                "sheet_name": sheet["sheet_name"],
                "energy": sheet["energy"],
                "rep0": rep0,
                "df_raw": sheet["df"],
                "warnings": warnings_by_sheet.get(sheet["sheet_name"], []),
            }
        )
    return sheet_results


def _qf_distribution_bar_html(qf_distribution: dict[str, int], strings: dict[str, str]) -> str:
    """
    Monta uma barra horizontal de distribuição de QF como HTML puro, com um
    segmento colorido por categoria (QF0-QF3/INDETERMINATE) proporcional à
    contagem.

    st.progress não suporta cores customizadas por segmento -- por isso a
    barra é montada como HTML (via st.html) em vez de um widget nativo.
    """
    total = sum(qf_distribution.get(label, 0) for label in QF_BAR_COLORS)
    if total == 0:
        no_measurements = strings["qf_bar_no_measurements"]
        return f'<div style="font-size:13px; color:#888;">{no_measurements}</div>'

    segments = []
    for label, color in QF_BAR_COLORS.items():
        count = qf_distribution.get(label, 0)
        if count == 0:
            continue
        pct = count / total * 100
        # Rótulo dentro do segmento só quando há espaço para não estourar o
        # texto de segmentos estreitos; a contagem exata sempre fica
        # disponível via title (tooltip ao passar o mouse).
        inner_label = f"{count}" if pct >= 6 else ""
        segments.append(
            f'<div title="{label}: {count} ({pct:.1f}%)" '
            f'style="flex:{pct} 0 0%; min-width:2px; background:{color}; '
            f"display:flex; align-items:center; justify-content:center; "
            f'color:#fff; font-size:12px; font-family:sans-serif; height:28px;">'
            f"{inner_label}</div>"
        )

    bar = (
        '<div style="display:flex; width:100%; border-radius:6px; '
        'overflow:hidden; border:1px solid rgba(128,128,128,0.3);">'
        + "".join(segments)
        + "</div>"
    )
    legend = "".join(
        '<span style="display:inline-flex; align-items:center; '
        'margin-right:14px; font-size:12px; font-family:sans-serif;">'
        f'<span style="width:10px; height:10px; border-radius:2px; '
        f'background:{color}; display:inline-block; margin-right:4px;">'
        f"</span>{label}</span>"
        for label, color in QF_BAR_COLORS.items()
    )
    return bar + f'<div style="margin-top:6px;">{legend}</div>'


def _render_energy_visual_summary(
    energy: str, stats: dict, flagged: list[dict], strings: dict[str, str]
) -> None:
    """
    Renderiza o sumário visual de uma energia: cards de métricas, barra de
    distribuição de QF, contagem de ALERT/CRITICAL por módulo (QC1-QC5) e a
    lista de profundidades com Review=YES (causa principal + evidências).
    """
    qf = stats["qf_distribution"]
    cols = st.columns(6)
    cols[0].metric(strings["metric_n_rep0"], stats["n_measurements"])
    cols[1].metric(strings["metric_qf0"], qf["QF0"])
    cols[2].metric(strings["metric_qf1"], qf["QF1"])
    cols[3].metric(strings["metric_qf2"], qf["QF2"])
    cols[4].metric(strings["metric_qf3"], qf["QF3"])
    cols[5].metric(strings["metric_qf_indeterminate"], qf["INDETERMINATE"])

    st.html(_qf_distribution_bar_html(qf, strings))

    st.markdown(f"**{strings['module_alert_critical_header']}**")
    module_rows = [
        {
            strings["module_col_header"]: module_col.replace("_State", ""),
            "ALERT": counts["ALERT"],
            "CRITICAL": counts["CRITICAL"],
        }
        for module_col, counts in stats["module_counts"].items()
    ]
    st.dataframe(pd.DataFrame(module_rows), width="stretch", hide_index=True)

    st.markdown(f"**{strings['flagged_header']}**")
    energy_flagged = [item for item in flagged if item["energy"] == energy]
    if energy_flagged:
        flagged_df = pd.DataFrame(energy_flagged)[
            ["sheet_name", "depth", "cause", "evidence"]
        ].rename(
            columns={
                "sheet_name": strings["flagged_col_sheet"],
                "depth": strings["flagged_col_depth"],
                "cause": strings["flagged_col_cause"],
                "evidence": strings["flagged_col_evidence"],
            }
        )
        st.dataframe(flagged_df, width="stretch", hide_index=True)
    else:
        st.caption(strings["no_flagged_caption"])


def _render_visual_summary(summary: dict, strings: dict[str, str]) -> None:
    """
    Renderiza o sumário visual completo, uma seção por energia processada.
    Usa st.tabs para navegar entre energias quando o arquivo tem múltiplas
    abas; para arquivo de aba única, renderiza direto (sem abas).
    """
    energies = summary["energies"]
    energy_names = list(energies.keys())

    if len(energy_names) > 1:
        tabs = st.tabs(energy_names)
        for tab, energy in zip(tabs, energy_names):
            with tab:
                _render_energy_visual_summary(
                    energy, energies[energy], summary["flagged"], strings
                )
    else:
        for energy in energy_names:
            _render_energy_visual_summary(energy, energies[energy], summary["flagged"], strings)


def _render_history_tab(strings: dict[str, str]) -> None:
    """
    Aba "Histórico": consulta qc_audit.query_runs e exibe as execuções já
    registradas, com filtros opcionais por arquivo e por operador.
    """
    st.subheader(strings["history_header"])

    col1, col2, col3 = st.columns([2, 2, 1])
    arquivo_filter = col1.text_input(
        strings["history_filter_file"], value="", key="hist_arquivo"
    )
    operador_filter = col2.text_input(
        strings["history_filter_operator"], value="", key="hist_operador"
    )
    limite = col3.number_input(
        strings["history_limit_label"], min_value=1, max_value=500, value=50, step=10,
        key="hist_limite",
    )

    history_df = query_runs(
        arquivo_nome=arquivo_filter or None,
        operador=operador_filter or None,
        limite=int(limite),
    )

    if history_df.empty:
        st.caption(strings["history_empty_caption"])
    else:
        st.dataframe(history_df, width="stretch", hide_index=True)


def _render_processing_tab(operador: str | None, strings: dict[str, str]) -> None:
    """
    Aba "Processamento": fluxo completo de upload, validação, execução do
    QC, resumo/sumário visual, resultados e download -- igual ao fluxo
    original da V2, apenas extraído para função para conviver com a aba
    "Histórico" em main().

    Registra a execução em auditoria (qc_audit.register_run) logo após um
    processamento bem-sucedido; falha ao registrar não impede o restante do
    fluxo (resumo/download continuam funcionando normalmente).
    """
    uploaded = st.file_uploader(strings["upload_label"], type=["xlsx"])
    if uploaded is None:
        st.info(strings["upload_info"])
        return

    try:
        sheets, skipped = read_workbook(uploaded)
    except Exception as exc:
        st.error(strings["workbook_read_error"].format(error=exc))
        return

    if not sheets:
        st.error(strings["no_sheets_error"])
        return

    st.caption(
        strings["sheets_found_caption"].format(
            sheets=", ".join(f"{s['sheet_name']} ({s['energy']})" for s in sheets)
        )
    )
    if skipped:
        st.warning(strings["sheets_skipped_warning"].format(sheets=", ".join(skipped)))

    st.subheader(strings["validation_header"])
    valid_sheets, warnings_by_sheet = _validate_sheets(sheets)
    if not valid_sheets:
        st.error(strings["no_valid_sheets_error"])
        return

    if st.button(strings["run_qc_button"]):
        start = time.perf_counter()
        sheet_results = _run_pipeline(valid_sheets, warnings_by_sheet)
        elapsed = time.perf_counter() - start

        try:
            register_run(
                sheet_results,
                arquivo_nome=uploaded.name,
                arquivo_bytes=uploaded.getvalue(),
                operador=operador,
                tempo_execucao_s=elapsed,
            )
        except Exception as exc:
            st.warning(strings["audit_register_warning"].format(error=exc))

        st.session_state["sheet_results"] = sheet_results
        st.session_state["file_name"] = uploaded.name

    sheet_results = st.session_state.get("sheet_results")
    file_name = st.session_state.get("file_name")
    if not sheet_results or file_name != uploaded.name:
        return

    st.subheader(strings["summary_header"])
    summary = build_summary(sheet_results, file_name=file_name)
    for energy, stats in summary["energies"].items():
        st.markdown(f"**{energy}**")
        qf = stats["qf_distribution"]
        cols = st.columns(6)
        cols[0].metric(strings["metric_n_rep0"], stats["n_measurements"])
        cols[1].metric(strings["metric_qf0"], qf["QF0"])
        cols[2].metric(strings["metric_qf1"], qf["QF1"])
        cols[3].metric(strings["metric_qf2"], qf["QF2"])
        cols[4].metric(strings["metric_qf3"], qf["QF3"])
        cols[5].metric(strings["metric_qf_indeterminate"], qf["INDETERMINATE"])

    st.subheader(strings["visual_summary_header"])
    _render_visual_summary(summary, strings)

    st.subheader(strings["results_header"])
    for result in sheet_results:
        st.caption(f"{result['sheet_name']} ({result['energy']})")
        st.dataframe(result["rep0"], width="stretch")

    st.subheader(strings["download_header"])
    stem = Path(file_name).stem
    st.download_button(
        strings["download_excel_label"],
        data=build_excel_report(sheet_results),
        file_name=f"{stem}_QC.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        strings["download_summary_label"],
        data=format_summary_text(summary),
        file_name=f"{stem}_resumo.txt",
        mime="text/plain",
    )


def _select_language() -> str:
    """
    Seletor de idioma da sidebar: EN é o padrão (primeiro em
    i18n.SUPPORTED_LANGS), PT a alternativa. O nome de cada idioma exibido
    na lista vem do próprio locale (`language_name`), nunca hardcoded aqui.
    """
    # Import local (não no topo do módulo): LEGACY/ tem seu próprio i18n.py
    # com nome idêntico. test_qc_core_vs_legacy.py insere LEGACY/ em
    # sys.path para carregar LEGACY/qc_core.py, que por sua vez importa
    # "i18n" (o dele). Se o "i18n" da V2 já estivesse em sys.modules antes
    # disso (import no topo deste módulo, executado por test_imports.py),
    # esse cache seria reaproveitado no lugar do i18n.py de LEGACY,
    # quebrando aquele teste. Import local evita a colisão sem tocar em
    # nenhum teste existente.
    import i18n

    names = [i18n.load(code)["language_name"] for code in i18n.SUPPORTED_LANGS]
    label = i18n.load(i18n.DEFAULT_LANG)["language_selector_label"]
    selected_name = st.sidebar.selectbox(label, options=names, index=0, key="qc_lang")
    return i18n.SUPPORTED_LANGS[names.index(selected_name)]


def main() -> None:
    """Ponto de entrada da UI."""
    import i18n  # ver comentário sobre import local em _select_language()

    # page_title é idêntico em todos os locales -- pode ser resolvido antes
    # do seletor de idioma, já que st.set_page_config precisa ser a
    # primeira chamada do Streamlit na página.
    st.set_page_config(page_title=i18n.load(i18n.DEFAULT_LANG)["page_title"], layout="wide")

    lang = _select_language()
    strings = i18n.load(lang)

    st.image(str(LOGO_PATH), width=200)
    st.title(strings["app_title"])
    st.caption(strings["app_caption"])

    operador = (
        st.sidebar.text_input(
            strings["sidebar_operator_label"],
            value="",
            help=strings["sidebar_operator_help"],
        ).strip()
        or None
    )

    tab_processing, tab_history = st.tabs([strings["tab_processing"], strings["tab_history"]])
    with tab_processing:
        _render_processing_tab(operador, strings)
    with tab_history:
        _render_history_tab(strings)


if __name__ == "__main__":
    main()
