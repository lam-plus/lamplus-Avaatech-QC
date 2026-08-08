"""
Configuração compartilhada dos testes da V2.

Garante que os módulos em `src/` (qc_config, qc_io, qc_core, ...) sejam
importáveis diretamente (ex. `import qc_io`) sem adicionar `LEGACY/` ao
PYTHONPATH (ver DEVELOPMENT.md, seção 2).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DATA_DIR = SRC_DIR.parent / "data" / "examples"
LOCALES_DIR = SRC_DIR / "locales"


def load_locale_strings(lang: str) -> dict[str, str]:
    """
    Lê src/locales/<lang>.json direto (sem `import i18n`), para testes que
    precisam do dict `strings` do i18n (ex. check_columns, format_summary_text).

    Um `import i18n` num módulo de teste ficaria em sys.modules pelo resto
    da sessão do pytest e colidiria com o `i18n.py` da LEGACY, carregado sob
    o mesmo nome por test_qc_core_vs_legacy.py -- ver comentário em
    qc_avaatech._select_language. Ler o JSON direto evita a colisão.
    """
    with (LOCALES_DIR / f"{lang}.json").open(encoding="utf-8") as fh:
        return json.load(fh)
