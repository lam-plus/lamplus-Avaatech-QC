"""
LAM+ Core QC — i18n.py
Bilingual (PT/EN) text loader. Reads translations from locales/<lang>.json.

Uso:
    from i18n import TEXTS, CHECK_MESSAGES

    lang = "pt"  # ou "en"
    T = TEXTS[lang]
    st.title(T["app_title"])
"""

import json
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
DEFAULT_LANG = "pt"
SUPPORTED_LANGS = ["pt", "en"]


def _load_locale(lang):
    path = LOCALES_DIR / f"{lang}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_RAW = {lang: _load_locale(lang) for lang in SUPPORTED_LANGS}

# Textos de UI (tudo exceto a seção "check", reservada para qc_core.check_file)
TEXTS = {
    lang: {k: v for k, v in data.items() if k != "check"}
    for lang, data in _RAW.items()
}

# Mensagens de check_file, indexadas por chave e depois por idioma:
# CHECK_MESSAGES["missing_columns"]["pt"] -> "Colunas obrigatórias ausentes: {cols}"
CHECK_MESSAGES = {}
for lang, data in _RAW.items():
    for key, template in data.get("check", {}).items():
        CHECK_MESSAGES.setdefault(key, {})[lang] = template
