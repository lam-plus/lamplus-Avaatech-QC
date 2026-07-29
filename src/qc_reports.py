"""
LAM+ Core QC V2 — qc_reports.py

Responsabilidade: exportação dos resultados em Excel e geração de resumo
simples. Não contém cálculo científico (isso é responsabilidade de
qc_core.py) nem lógica de interface (qc_avaatech.py). Não importa nada de
LEGACY/.
"""

from __future__ import annotations

from typing import Any


def build_excel_report(sheet_results: list[dict]) -> bytes:
    """
    Serializa os resultados de todas as abas processadas com sucesso num
    único workbook .xlsx para download.

    Entrada:
        sheet_results: list[dict], um item por aba processada, cada um
            contendo pelo menos "sheet_name" (str), "energy" (str) e
            "rep0" (DataFrame já processado por qc_core.run_qc).

    Saída:
        Bytes do arquivo .xlsx pronto para download/gravação.

    Contrato:
        - Uma aba de saída por aba de entrada, preservando o nome original
          e as colunas originais do instrumento sem alteração.
        - Colunas de QC (z-scores, estados, QF, causas) são adicionadas,
          nunca substituem colunas originais.
        - Não achata nem combina abas de energias diferentes.
    """
    raise NotImplementedError


def build_summary(sheet_results: list[dict]) -> dict[str, Any]:
    """
    Gera um resumo simples dos resultados processados (contagens por QF,
    por energia, causas mais frequentes).

    Entrada:
        sheet_results: mesma estrutura de build_excel_report.

    Saída:
        dict com o resumo agregado. Estrutura exata (chaves/formato) a
        confirmar na Etapa 6 — este contrato garante apenas que a entrada
        é a lista de resultados por aba e a saída é um dict serializável.

    Contrato:
        - Não modifica `sheet_results` nem os DataFrames nele contidos.
        - QualityFlag.INDETERMINATE é contado separadamente de QF0-QF3,
          nunca somado a QF0.
    """
    raise NotImplementedError
