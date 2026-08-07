"""
LAM+ Core QC V2 — i18n.py

Suporte bilíngue mínimo para a interface (qc_avaatech.py): carrega as
strings de src/locales/<lang>.json. EN é o idioma padrão; se uma chave não
existir no idioma pedido, cai para o valor em EN -- a interface nunca
levanta KeyError por falta de tradução.

Não contém nenhuma lógica de QC e não é importado por qc_core.py,
qc_io.py ou qc_config.py.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DEFAULT_LANG = "en"

# Idiomas com arquivo de tradução em src/locales/. EN é sempre o primeiro
# (padrão); a ordem aqui também define a ordem do seletor na sidebar.
SUPPORTED_LANGS = ("en", "pt")

LOCALES_DIR = Path(__file__).resolve().parent / "locales"


@lru_cache(maxsize=None)
def _load_raw(lang: str) -> dict[str, str]:
    """Lê src/locales/<lang>.json. Levanta FileNotFoundError se não existir."""
    path = LOCALES_DIR / f"{lang}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load(lang: str = DEFAULT_LANG) -> dict[str, str]:
    """
    Carrega as strings de interface do idioma `lang`.

    Saída:
        dict[str, str] com todas as chaves de en.json. Para `lang` != EN,
        cada chave ausente na tradução (ou o idioma inteiro, se
        desconhecido) é preenchida com o valor correspondente em EN.

    Contrato:
        - Nunca levanta KeyError na interface por chave/tradução faltando.
        - `lang` desconhecido (sem arquivo em locales/) equivale a EN.
    """
    en = _load_raw(DEFAULT_LANG)
    if lang == DEFAULT_LANG:
        return dict(en)
    try:
        translated = _load_raw(lang)
    except FileNotFoundError:
        return dict(en)
    return {**en, **translated}
