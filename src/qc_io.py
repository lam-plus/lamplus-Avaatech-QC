"""
LAM+ Core QC V2 — qc_io.py

Responsabilidade: leitura de workbooks Avaatech, detecção de energia por
aba e validação estrutural (colunas obrigatórias, Rep0, réplicas).

Não contém cálculo científico (isso é responsabilidade de qc_core.py) nem
lógica de interface (qc_avaatech.py). Não importa nada de LEGACY/.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from qc_config import (
    CORE_DEPTH_COL,
    DEPTH_COL,
    ENERGY_VARIABLES,
    REP0_LABEL,
    REPLICATE_COL,
    REPLICATE_KEY_COLS,
    SUPPORTED_ENERGIES,
)


def _energy_variables(energy: str) -> dict[str, str | None]:
    """Valida `energy` e devolve o dict de variáveis físicas correspondente."""
    if energy not in ENERGY_VARIABLES:
        raise ValueError(
            f"Energia desconhecida: '{energy}'. Válidas: {list(SUPPORTED_ENERGIES)}."
        )
    return ENERGY_VARIABLES[energy]


def detect_energy(sheet_name: str) -> str:
    """
    Detecta a energia (uma de SUPPORTED_ENERGIES) a partir do nome de uma
    aba do workbook.

    Entrada:
        sheet_name: nome bruto da aba, como retornado por pandas/openpyxl.

    Saída:
        Uma das strings em SUPPORTED_ENERGIES.

    Contrato:
        - Levanta ValueError quando a energia não pode ser inferida do nome.
        - Não lê nem valida o conteúdo da aba — só o nome.
    """
    name = str(sheet_name).lower()
    for energy in SUPPORTED_ENERGIES:
        digits = "".join(ch for ch in energy if ch.isdigit())
        if digits in name:
            return energy
    raise ValueError(
        f"Energia não reconhecida a partir do nome da aba: '{sheet_name}'. "
        f"Nomes de aba devem conter um dos identificadores {list(SUPPORTED_ENERGIES)} "
        "(ex. '10kV', '30 kV', '50KV')."
    )


def read_workbook(file_or_buffer: Any) -> tuple[list[dict], list[str]]:
    """
    Lê todas as abas de um workbook Avaatech e detecta a energia de cada
    uma pelo nome.

    Entrada:
        file_or_buffer: caminho de arquivo ou objeto file-like (.xlsx).

    Saída:
        sheets: list[dict] — um item por aba processável, cada um com pelo
            menos as chaves "sheet_name" (str), "energy" (str, uma de
            SUPPORTED_ENERGIES) e "df" (pandas.DataFrame bruto, sem filtro
            de réplica nem validação).
        skipped: list[str] — nomes de abas cuja energia não pôde ser
            inferida e que, por isso, não entraram em `sheets`.

    Contrato:
        - Não executa validação estrutural nem cálculo — só localiza e
          classifica abas por energia (ver check_columns/run_qc).
        - Não modifica os DataFrames retornados.
        - Uma aba cuja energia não pôde ser inferida do nome é sempre
          movida para `skipped`, mesmo quando é a única aba do workbook
          (simplificação deliberada da V2 em relação à LEGACY: sem exceção
          de "aba única assume DEFAULT_ENERGY" — reduz opções implícitas,
          ver DEVELOPMENT.md 4.1).
    """
    xls = pd.ExcelFile(file_or_buffer)
    sheets: list[dict] = []
    skipped: list[str] = []
    for name in xls.sheet_names:
        try:
            energy = detect_energy(name)
        except ValueError:
            skipped.append(name)
            continue
        df = xls.parse(sheet_name=name)
        sheets.append({"sheet_name": name, "energy": energy, "df": df})
    return sheets, skipped


def resolve_depth_column(df: pd.DataFrame) -> tuple[str, list[str]]:
    """
    Determina qual coluna usar como profundidade contínua para ordenar as
    medições de uma aba: DEPTH_COL (CompositeDepth (mm)) quando presente,
    com fallback para CORE_DEPTH_COL (CoreDepth) quando ausente.

    Entrada:
        df: DataFrame bruto de uma aba.

    Saída:
        depth_col: nome da coluna a usar como profundidade contínua.
        warnings: lista com um aviso explícito quando o fallback foi usado
            (vazia quando DEPTH_COL está presente no arquivo).

    Contrato:
        - Levanta ValueError se nem DEPTH_COL nem CORE_DEPTH_COL estiverem
          presentes em `df` — nesse caso não há profundidade utilizável.
    """
    if DEPTH_COL in df.columns:
        return DEPTH_COL, []
    if CORE_DEPTH_COL in df.columns:
        return CORE_DEPTH_COL, [
            f"Coluna '{DEPTH_COL}' não encontrada; usando '{CORE_DEPTH_COL}' "
            "como profundidade contínua. Isso só é correto para testemunhos "
            "de seção única — em testemunhos multi-seção, CoreDepth reinicia "
            "a cada seção e pode distorcer a ordenação por profundidade."
        ]
    raise ValueError(
        f"Nenhuma coluna de profundidade encontrada ('{DEPTH_COL}' ou "
        f"'{CORE_DEPTH_COL}'). Verifique se o workbook foi exportado "
        "corretamente pelo Avaatech."
    )


def check_columns(
    df: pd.DataFrame, energy: str, strings: dict[str, str]
) -> tuple[list[str], list[str]]:
    """
    Valida a estrutura de uma única aba/energia antes de rodar o pipeline.

    Entrada:
        df: DataFrame bruto de uma aba (como retornado por read_workbook).
        energy: uma de SUPPORTED_ENERGIES — determina quais colunas são
            obrigatórias para essa energia (ver qc_config.ENERGY_VARIABLES).
        strings: dict de strings do i18n (ver i18n.load) -- todas as
            mensagens de `errors`/`warnings` vêm das chaves "validation_*"
            deste dict, nunca hardcoded aqui. qc_io.py não importa i18n.py
            (ver contrato do módulo); quem chama (ex. qc_avaatech.py)
            resolve o idioma e passa o dict já carregado.

    Saída:
        errors: list[str] — problemas que bloqueiam a execução do pipeline
            (ex. coluna obrigatória ausente, Rep0 ausente).
        warnings: list[str] — problemas que não bloqueiam, mas devem ser
            comunicados ao usuário (ex. profundidades duplicadas).

    Contrato:
        - Mensagens em `errors`/`warnings` devem ser acionáveis (dizer o
          que falta e, quando possível, o que fazer).
        - Não lança exceção para dados de entrada inválidos — reporta via
          `errors`; quem chama decide se bloqueia.
        - O idioma das mensagens é inteiramente determinado por `strings`.
    """
    errors: list[str] = []
    warnings: list[str] = []

    cfg = _energy_variables(energy)

    required = [REPLICATE_COL, cfg["throughput"], *REPLICATE_KEY_COLS]
    if cfg["coherent"] is not None:
        required.append(cfg["coherent"])
    if cfg["incoherent"] is not None:
        required.append(cfg["incoherent"])

    missing = [c for c in required if c not in df.columns]
    if missing:
        errors.append(
            strings["validation_missing_columns"].format(
                energy=energy, columns=", ".join(missing)
            )
        )

    try:
        _, depth_warnings = resolve_depth_column(df)
        if depth_warnings:
            warnings.append(
                strings["validation_depth_fallback"].format(
                    depth_col=DEPTH_COL, core_depth_col=CORE_DEPTH_COL
                )
            )
    except ValueError:
        # Já reportado como erro acima quando CORE_DEPTH_COL faz parte de
        # REPLICATE_KEY_COLS (sempre obrigatório); mensagem própria caso
        # falte só a profundidade (ex. checagem chamada fora de ordem).
        if CORE_DEPTH_COL not in missing:
            errors.append(
                strings["validation_no_depth_column"].format(
                    depth_col=DEPTH_COL, core_depth_col=CORE_DEPTH_COL
                )
            )

    if REPLICATE_COL in df.columns:
        rep_values = df[REPLICATE_COL].dropna()
        if REP0_LABEL not in rep_values.values:
            errors.append(
                strings["validation_no_rep0"].format(
                    rep0_label=REP0_LABEL, replicate_col=REPLICATE_COL
                )
            )

    return errors, warnings


def select_rep0(df: pd.DataFrame) -> pd.DataFrame:
    """
    Seleciona as medições Rep0 de uma aba já lida.

    Entrada:
        df: DataFrame bruto de uma aba, contendo a coluna REPLICATE_COL.

    Saída:
        DataFrame contendo apenas as linhas com REPLICATE_COL == REP0_LABEL.

    Contrato:
        - Levanta ValueError se REPLICATE_COL não existir em `df` ou se
          nenhuma linha Rep0 for encontrada — chamar check_columns antes
          para obter uma mensagem de validação amigável em vez de exceção.
        - Não modifica `df` original (retorna cópia/view independente).
    """
    if REPLICATE_COL not in df.columns:
        raise ValueError(
            f"Coluna '{REPLICATE_COL}' ausente do DataFrame. Rode "
            "check_columns antes de select_rep0 para obter uma mensagem de "
            "validação acionável."
        )
    rep0 = df[df[REPLICATE_COL] == REP0_LABEL].copy()
    if rep0.empty:
        raise ValueError(
            f"Nenhuma medição '{REP0_LABEL}' encontrada na coluna "
            f"'{REPLICATE_COL}'. Rode check_columns antes de select_rep0 "
            "para obter uma mensagem de validação acionável."
        )
    return rep0


def detect_replicates(df: pd.DataFrame) -> list[str]:
    """
    Lista os rótulos de réplica presentes em uma aba (ex. ["Rep0"],
    ["Rep0", "Rep1"], ["Rep0", "Rep1", "Rep2"]).

    Entrada:
        df: DataFrame bruto de uma aba, contendo a coluna REPLICATE_COL.

    Saída:
        Lista dos valores únicos de REPLICATE_COL presentes, na ordem de
        primeira ocorrência.

    Contrato:
        - Não assume que réplicas além de Rep0 existem — arquivos sem
          réplicas adicionais são válidos (QC5 fica sem dado para casar,
          não é erro estrutural).
        - Levanta ValueError se REPLICATE_COL não existir em `df` (mesmo
          padrão de select_rep0 — chamar check_columns antes).
        - Linhas totalmente em branco (sem réplica atribuída, ex. linhas
          separadoras entre seções em alguns exports) são ignoradas: NaN
          não é um rótulo de réplica válido.
    """
    if REPLICATE_COL not in df.columns:
        raise ValueError(
            f"Coluna '{REPLICATE_COL}' ausente do DataFrame. Rode "
            "check_columns antes de detect_replicates para obter uma "
            "mensagem de validação acionável."
        )
    seen: list[str] = []
    for value in df[REPLICATE_COL].dropna():
        if value not in seen:
            seen.append(value)
    return seen
