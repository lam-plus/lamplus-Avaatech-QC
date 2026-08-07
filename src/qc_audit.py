"""
LAM+ Core QC V2 — qc_audit.py

Responsabilidade: trilha de auditoria das execuções do pipeline, persistida
em SQLite (data/audit.db). Uma linha por aba/energia processada com sucesso:
quem rodou, qual arquivo (nome + MD5), qual commit/versão do código e a
distribuição de QF resultante.

Não contém cálculo científico (isso é responsabilidade de qc_core.py) nem
lógica de interface (qc_avaatech.py). Não importa nada de LEGACY/.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from qc_config import PIPELINE_VERSION
from qc_reports import format_quality_flag

# Banco de auditoria vive em data/audit.db (irmão de src/), mesmo diretório
# usado pelos demais artefatos de dados do projeto -- nunca dentro de src/.
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "audit.db"

TABLE_NAME = "runs"

_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    operador TEXT,
    arquivo_nome TEXT NOT NULL,
    arquivo_md5 TEXT NOT NULL,
    git_commit TEXT,
    pipeline_versao TEXT NOT NULL,
    aba TEXT NOT NULL,
    n_rep0 INTEGER NOT NULL,
    qf0 INTEGER NOT NULL,
    qf1 INTEGER NOT NULL,
    qf2 INTEGER NOT NULL,
    qf3 INTEGER NOT NULL,
    qf_indeterminate INTEGER NOT NULL,
    avisos TEXT,
    tempo_execucao_s REAL
)
"""

# Colunas de `runs`, na ordem exata da tabela -- usada tanto para o INSERT
# quanto para garantir que query_runs devolva um DataFrame com estas colunas
# mesmo quando não há nenhuma linha (banco novo/filtro sem resultado).
RUNS_COLUMNS = (
    "id",
    "timestamp",
    "operador",
    "arquivo_nome",
    "arquivo_md5",
    "git_commit",
    "pipeline_versao",
    "aba",
    "n_rep0",
    "qf0",
    "qf1",
    "qf2",
    "qf3",
    "qf_indeterminate",
    "avisos",
    "tempo_execucao_s",
)


def init_db(db_path: str | Path = DB_PATH) -> None:
    """
    Cria o arquivo do banco (e diretório pai, se necessário) e a tabela
    `runs`, se ainda não existirem.

    Contrato:
        - Idempotente: chamar várias vezes não apaga nem duplica dados
          (CREATE TABLE IF NOT EXISTS).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()


def _get_git_commit(cwd: str | Path | None = None) -> str | None:
    """
    Tenta obter o hash curto do commit git atual via subprocess.

    Saída:
        Hash curto (str) ou None quando git não está instalado, o diretório
        não é um repositório git, ou qualquer outro erro ocorre.

    Contrato:
        - Nunca levanta exceção -- git indisponível é um caso esperado
          (ex. instalação via executável empacotado, sem .git presente).
    """
    cwd = Path(cwd) if cwd is not None else Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except Exception:
        # Cobre FileNotFoundError (git não instalado), CalledProcessError
        # (fora de um repo git), TimeoutExpired e qualquer outra falha --
        # git é um dado auxiliar de rastreabilidade, nunca deve bloquear
        # o registro de auditoria.
        return None
    commit = result.stdout.strip()
    return commit or None


def _qf_counts(qf_values: Any) -> dict[str, int]:
    """Conta rótulos de QF ('QF0'..'QF3'/'INDETERMINATE') em uma coluna QF."""
    counts = {"QF0": 0, "QF1": 0, "QF2": 0, "QF3": 0, "INDETERMINATE": 0}
    for qf in qf_values:
        counts[format_quality_flag(qf)] += 1
    return counts


def register_run(
    results: list[dict],
    arquivo_nome: str,
    arquivo_bytes: bytes,
    operador: str | None = None,
    *,
    tempo_execucao_s: float | None = None,
    db_path: str | Path = DB_PATH,
) -> list[int]:
    """
    Registra uma execução do pipeline no banco de auditoria: uma linha por
    aba/energia processada com sucesso.

    Entrada:
        results: lista no formato de sheet_results (qc_avaatech._run_pipeline)
            -- cada item precisa de "sheet_name" (str), "energy" (str) e
            "rep0" (DataFrame já processado por qc_core.run_qc, com a coluna
            "QF"). A chave opcional "warnings" (list[str]) é serializada na
            coluna `avisos`; ausente/vazia quando não houver avisos.
        arquivo_nome: nome do arquivo original (ex. uploaded.name).
        arquivo_bytes: conteúdo bruto do arquivo, usado para calcular o MD5.
        operador: texto livre opcional identificando quem rodou o QC.
        tempo_execucao_s: duração da execução do pipeline em segundos
            (opcional -- quem chama mede o tempo, este módulo só persiste).
        db_path: caminho do banco SQLite (DB_PATH por padrão; parametrizável
            para testes).

    Saída:
        Lista de ids inseridos, na mesma ordem de `results`.

    Contrato:
        - Cria o banco/tabela se ainda não existirem (via init_db).
        - MD5 é determinístico: mesmo conteúdo de arquivo produz sempre o
          mesmo hash, entre execuções.
        - git indisponível nunca causa falha -- git_commit fica None.
        - Não modifica `results`.
    """
    init_db(db_path)

    arquivo_md5 = hashlib.md5(arquivo_bytes).hexdigest()
    git_commit = _get_git_commit()
    timestamp = datetime.now(timezone.utc).isoformat()

    inserted_ids: list[int] = []
    with sqlite3.connect(db_path) as conn:
        for result in results:
            rep0 = result["rep0"]
            qf_counts = _qf_counts(rep0["QF"])
            avisos = result.get("warnings", [])
            cur = conn.execute(
                f"""
                INSERT INTO {TABLE_NAME} (
                    timestamp, operador, arquivo_nome, arquivo_md5, git_commit,
                    pipeline_versao, aba, n_rep0, qf0, qf1, qf2, qf3,
                    qf_indeterminate, avisos, tempo_execucao_s
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    operador,
                    arquivo_nome,
                    arquivo_md5,
                    git_commit,
                    PIPELINE_VERSION,
                    result["energy"],
                    len(rep0),
                    qf_counts["QF0"],
                    qf_counts["QF1"],
                    qf_counts["QF2"],
                    qf_counts["QF3"],
                    qf_counts["INDETERMINATE"],
                    json.dumps(avisos, ensure_ascii=False),
                    tempo_execucao_s,
                ),
            )
            inserted_ids.append(cur.lastrowid)
        conn.commit()

    return inserted_ids


def query_runs(
    arquivo_nome: str | None = None,
    operador: str | None = None,
    limite: int = 50,
    *,
    db_path: str | Path = DB_PATH,
) -> pd.DataFrame:
    """
    Consulta o histórico de execuções em `runs`, mais recentes primeiro.

    Entrada:
        arquivo_nome: filtro exato opcional por nome de arquivo.
        operador: filtro exato opcional por operador.
        limite: número máximo de linhas retornadas.
        db_path: caminho do banco SQLite (DB_PATH por padrão; parametrizável
            para testes).

    Saída:
        DataFrame pandas com as colunas de RUNS_COLUMNS, ordenado por id
        decrescente (execução mais recente primeiro). Vazio (mas com as
        colunas corretas) quando o banco ainda não existe ou nenhum
        registro satisfaz os filtros.

    Contrato:
        - Cria o banco/tabela se ainda não existirem (via init_db) -- nunca
          levanta erro por o arquivo .db não existir ainda.
        - Filtros são combinados por AND; None/"" desativa o filtro.
    """
    init_db(db_path)

    query = f"SELECT * FROM {TABLE_NAME} WHERE 1=1"
    params: list[Any] = []
    if arquivo_nome:
        query += " AND arquivo_nome = ?"
        params.append(arquivo_nome)
    if operador:
        query += " AND operador = ?"
        params.append(operador)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limite)

    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params)

    return df if not df.empty else pd.DataFrame(columns=RUNS_COLUMNS)
