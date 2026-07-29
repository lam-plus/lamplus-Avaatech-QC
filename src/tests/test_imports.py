"""
Testes de importação da V2 (Etapa 1 do plano-de-acao.md).

Verifica que:
    - todos os módulos da V2 importam sem erro;
    - nenhum módulo da V2 importa (direta ou indiretamente por texto-fonte)
      nada de LEGACY/.

Não depende de LEGACY/ estar no PYTHONPATH (ver DEVELOPMENT.md, seção 2).
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

MODULES = ["qc_config", "qc_io", "qc_core", "qc_reports", "qc_avaatech"]


def test_modules_import_without_error():
    for name in MODULES:
        importlib.import_module(name)


def test_no_module_imports_from_legacy():
    for name in MODULES:
        source_path = SRC_DIR / f"{name}.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "legacy" not in alias.name.lower(), (
                        f"{name}.py importa de LEGACY/: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "legacy" not in module.lower(), (
                    f"{name}.py importa de LEGACY/: {module}"
                )


def test_legacy_not_on_sys_path():
    legacy_dir = SRC_DIR.parent / "LEGACY"
    for entry in sys.path:
        assert Path(entry).resolve() != legacy_dir.resolve()
