"""
Configuração compartilhada dos testes da V2.

Garante que os módulos em `src/` (qc_config, qc_io, qc_core, ...) sejam
importáveis diretamente (ex. `import qc_io`) sem adicionar `LEGACY/` ao
PYTHONPATH (ver DEVELOPMENT.md, seção 2).
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DATA_DIR = SRC_DIR.parent / "data"
