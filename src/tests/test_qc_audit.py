"""
Testes de qc_audit.py (trilha de auditoria das execuções do pipeline).

Casos cobertos:
    - init_db cria o arquivo do banco e a tabela `runs` com as colunas
      esperadas;
    - register_run insere uma linha por aba e query_runs lê de volta com os
      valores corretos (contagem de QF, n_rep0, avisos);
    - MD5 do arquivo é determinístico para o mesmo conteúdo, entre chamadas
      independentes de register_run;
    - git indisponível (binário ausente, ou qualquer falha do subprocess)
      não impede o registro -- git_commit fica None;
    - query_runs filtra corretamente por arquivo_nome e por operador.

Cada teste usa seu próprio banco isolado em tmp_path (via `db_path=`) --
nunca toca data/audit.db real. Não depende de LEGACY/ (ver conftest.py).
"""

from __future__ import annotations

import hashlib
import sqlite3

import pandas as pd
import pytest

import qc_audit
from qc_config import QualityFlag
from qc_audit import RUNS_COLUMNS, init_db, query_runs, register_run


def _make_result(
    sheet_name: str = "10kV",
    energy: str = "10kV",
    qf_values: list | None = None,
    warnings: list[str] | None = None,
) -> dict:
    """Resultado sintético mínimo no formato de sheet_results (rep0 só
    precisa da coluna "QF" -- é tudo que register_run lê dele)."""
    if qf_values is None:
        qf_values = [
            QualityFlag.QF0,
            QualityFlag.QF0,
            QualityFlag.QF1,
            QualityFlag.QF2,
            QualityFlag.QF3,
            QualityFlag.INDETERMINATE,
        ]
    result = {
        "sheet_name": sheet_name,
        "energy": energy,
        "rep0": pd.DataFrame({"QF": qf_values}),
    }
    if warnings is not None:
        result["warnings"] = warnings
    return result


# ============================================================
# CRIAÇÃO DO BANCO E DA TABELA
# ============================================================


def test_init_db_creates_file_and_table(tmp_path):
    db_path = tmp_path / "audit.db"
    assert not db_path.exists()

    init_db(db_path)

    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(runs)")]
    assert cols == list(RUNS_COLUMNS)


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "audit.db"
    init_db(db_path)
    init_db(db_path)  # não deve levantar erro nem apagar a tabela

    with sqlite3.connect(db_path) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
    assert "runs" in tables


def test_query_runs_on_fresh_db_returns_empty_with_correct_columns(tmp_path):
    db_path = tmp_path / "audit.db"  # nunca inicializado explicitamente
    df = query_runs(db_path=db_path)
    assert df.empty
    assert list(df.columns) == list(RUNS_COLUMNS)


# ============================================================
# INSERÇÃO E LEITURA
# ============================================================


def test_register_run_inserts_one_row_per_sheet_and_query_runs_reads_it_back(
    tmp_path,
):
    db_path = tmp_path / "audit.db"
    result = _make_result(warnings=["aviso de teste"])

    ids = register_run(
        [result],
        arquivo_nome="arquivo.xlsx",
        arquivo_bytes=b"conteudo de teste",
        operador="andre",
        tempo_execucao_s=1.23,
        db_path=db_path,
    )

    assert len(ids) == 1

    df = query_runs(db_path=db_path)
    assert len(df) == 1
    row = df.iloc[0]

    assert row["arquivo_nome"] == "arquivo.xlsx"
    assert row["operador"] == "andre"
    assert row["aba"] == "10kV"
    assert row["n_rep0"] == 6
    assert row["qf0"] == 2
    assert row["qf1"] == 1
    assert row["qf2"] == 1
    assert row["qf3"] == 1
    assert row["qf_indeterminate"] == 1
    assert row["pipeline_versao"]  # não vazio
    assert row["timestamp"]  # não vazio
    assert "aviso de teste" in row["avisos"]
    assert row["tempo_execucao_s"] == pytest.approx(1.23)


def test_register_run_inserts_one_row_per_aba_for_multiple_sheets(tmp_path):
    db_path = tmp_path / "audit.db"
    results = [
        _make_result(sheet_name="10kV", energy="10kV"),
        _make_result(sheet_name="30kV", energy="30kV"),
        _make_result(sheet_name="50kV", energy="50kV"),
    ]

    ids = register_run(
        results, arquivo_nome="multi.xlsx", arquivo_bytes=b"multi", db_path=db_path
    )

    assert len(ids) == 3
    df = query_runs(db_path=db_path, limite=10)
    assert len(df) == 3
    assert set(df["aba"]) == {"10kV", "30kV", "50kV"}
    assert set(df["arquivo_nome"]) == {"multi.xlsx"}


def test_register_run_without_warnings_key_stores_empty_avisos(tmp_path):
    db_path = tmp_path / "audit.db"
    result = _make_result()  # sem "warnings"

    register_run([result], "sem_avisos.xlsx", b"x", db_path=db_path)

    df = query_runs(db_path=db_path)
    assert df.iloc[0]["avisos"] == "[]"


# ============================================================
# MD5 DETERMINÍSTICO
# ============================================================


def test_md5_is_deterministic_for_same_content(tmp_path):
    db_path = tmp_path / "audit.db"
    content = b"mesmo conteudo de arquivo"
    expected_md5 = hashlib.md5(content).hexdigest()

    register_run([_make_result()], "a.xlsx", content, db_path=db_path)
    register_run([_make_result()], "b.xlsx", content, db_path=db_path)

    df = query_runs(db_path=db_path, limite=10)
    assert set(df["arquivo_md5"]) == {expected_md5}


def test_md5_differs_for_different_content(tmp_path):
    db_path = tmp_path / "audit.db"

    register_run([_make_result()], "a.xlsx", b"conteudo 1", db_path=db_path)
    register_run([_make_result()], "b.xlsx", b"conteudo 2", db_path=db_path)

    df = query_runs(db_path=db_path, limite=10)
    assert len(set(df["arquivo_md5"])) == 2


# ============================================================
# GIT INDISPONÍVEL NÃO CAUSA FALHA
# ============================================================


def test_register_run_survives_git_binary_not_found(tmp_path, monkeypatch):
    def _raise_file_not_found(*args, **kwargs):
        raise FileNotFoundError("git não instalado")

    monkeypatch.setattr(qc_audit.subprocess, "run", _raise_file_not_found)

    db_path = tmp_path / "audit.db"
    ids = register_run([_make_result()], "sem_git.xlsx", b"x", db_path=db_path)

    assert len(ids) == 1
    df = query_runs(db_path=db_path)
    assert pd.isna(df.iloc[0]["git_commit"]) or df.iloc[0]["git_commit"] is None


def test_register_run_survives_git_called_process_error(tmp_path, monkeypatch):
    import subprocess as real_subprocess

    def _raise_called_process_error(*args, **kwargs):
        raise real_subprocess.CalledProcessError(128, ["git", "rev-parse"])

    monkeypatch.setattr(qc_audit.subprocess, "run", _raise_called_process_error)

    db_path = tmp_path / "audit.db"
    ids = register_run([_make_result()], "fora_de_repo.xlsx", b"x", db_path=db_path)

    assert len(ids) == 1
    df = query_runs(db_path=db_path)
    assert pd.isna(df.iloc[0]["git_commit"]) or df.iloc[0]["git_commit"] is None


def test_get_git_commit_returns_none_on_any_subprocess_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        qc_audit.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")),
    )
    assert qc_audit._get_git_commit() is None


# ============================================================
# FILTROS DE query_runs
# ============================================================


@pytest.fixture
def seeded_db(tmp_path):
    """Banco com 3 execuções: dois arquivos, dois operadores distintos."""
    db_path = tmp_path / "audit.db"
    register_run(
        [_make_result()], "core_A.xlsx", b"a", operador="ana", db_path=db_path
    )
    register_run(
        [_make_result()], "core_B.xlsx", b"b", operador="bruno", db_path=db_path
    )
    register_run(
        [_make_result()], "core_A.xlsx", b"a2", operador="bruno", db_path=db_path
    )
    return db_path


def test_query_runs_filters_by_arquivo_nome(seeded_db):
    df = query_runs(arquivo_nome="core_A.xlsx", db_path=seeded_db)
    assert len(df) == 2
    assert set(df["arquivo_nome"]) == {"core_A.xlsx"}


def test_query_runs_filters_by_operador(seeded_db):
    df = query_runs(operador="bruno", db_path=seeded_db)
    assert len(df) == 2
    assert set(df["operador"]) == {"bruno"}


def test_query_runs_filters_combine_with_and(seeded_db):
    df = query_runs(arquivo_nome="core_A.xlsx", operador="bruno", db_path=seeded_db)
    assert len(df) == 1
    assert df.iloc[0]["arquivo_nome"] == "core_A.xlsx"
    assert df.iloc[0]["operador"] == "bruno"


def test_query_runs_without_filters_returns_all_up_to_limite(seeded_db):
    df = query_runs(db_path=seeded_db, limite=2)
    assert len(df) == 2  # limite respeitado

    df_all = query_runs(db_path=seeded_db, limite=10)
    assert len(df_all) == 3


def test_query_runs_orders_most_recent_first(seeded_db):
    df = query_runs(db_path=seeded_db, limite=10)
    assert list(df["id"]) == sorted(df["id"], reverse=True)
