"""
LAM+ Core QC V2 — qc_config.py

Fonte única de verdade para constantes, energias, variáveis por energia,
limiares e estados de QC. Nenhum outro módulo da V2 deve redefinir esses
valores — apenas importá-los daqui.

Não importa nada de LEGACY/. Não contém lógica de cálculo.
"""

from enum import Enum, IntEnum

# ============================================================
# ENERGIAS SUPORTADAS
# ============================================================

# Energias de tubo de raio-X suportadas pelo Avaatech. Cada aba de um
# workbook multi-energia corresponde a uma destas.
SUPPORTED_ENERGIES = ("10kV", "30kV", "50kV")

DEFAULT_ENERGY = "10kV"

# Variáveis físicas medidas por energia. `None` indica que a energia não
# mede aquele parâmetro (ausência estrutural, não dado faltante pontual).
ENERGY_VARIABLES = {
    "10kV": {
        "throughput": "Throughput",
        "argon": "Ar-Ka Area",
        "coherent": "Rh-La Area",
        "incoherent": "Rh-La-Inc Area",
    },
    "30kV": {
        "throughput": "Throughput",
        "argon": None,
        "coherent": "Rh-Ka-Coh Area",
        "incoherent": "Rh-Ka-Inc Area",
    },
    "50kV": {
        "throughput": "Throughput",
        "argon": None,
        "coherent": None,
        "incoherent": None,
    },
}

# ============================================================
# COLUNAS ESTRUTURAIS
# ============================================================

# Profundidade contínua ao longo de todo o testemunho. Só é preenchida na
# primeira passada (Rep0); nas réplicas seguintes vem nula.
DEPTH_COL = "CompositeDepth (mm)"

# Profundidade local/por seção (reinicia a cada tubo de amostragem).
# Uso exclusivo de exibição — nunca em cálculo.
CORE_DEPTH_COL = "CoreDepth"

REPLICATE_COL = "Replicate Nr Count"

# Chave física para casar réplicas (Rep0/Rep1/Rep2/...). Nunca usar
# DEPTH_COL para esse propósito — ver plano-de-acao.md, achado C1.
REPLICATE_KEY_COLS = ("Spectrum", "CoreDepth")

REP0_LABEL = "Rep0"

# Elementos usados na avaliação de reprodutibilidade entre réplicas (QC5).
ELEMENTS_REPLICATES = (
    "Al-Ka Area",
    "Si-Ka Area",
    "K -Ka Area",
    "Ca-Ka Area",
    "Ti-Ka Area",
    "Fe-Ka Area",
)

# ============================================================
# PARÂMETROS DO QC4 — ROLLING
# ============================================================

ROLLING_WINDOW = 5

# ============================================================
# LIMIARES — Z-SCORE (QC1, QC2, QC3)
# ============================================================

Z_WARNING = 2.5
Z_CRITICAL = 3.5

# ============================================================
# LIMIARES — ROLLING (QC4)
# ============================================================

# QC4 no modo de contagem só distingue OK/ALERT (sem CRITICAL).
ROLLING_Z_ALERT = 4.0

# ============================================================
# LIMIARES — RPD (QC5)
# ============================================================

RPD_WARNING = 10.0
RPD_CRITICAL = 20.0

# ============================================================
# ESTADOS DOS MÓDULOS QC
# ============================================================


class QCState(str, Enum):
    """Estado individual de um módulo QC para uma linha/medição."""

    OK = "OK"
    ALERT = "ALERT"
    CRITICAL = "CRITICAL"

    # Módulo sem nada a avaliar nesta linha — por dois motivos possíveis:
    # (a) estruturalmente não aplicável à energia (ex. QC2/QC3 em 50 kV);
    # (b) não há segunda medição física para comparar nesta posição (QC5
    # sem Rep1/Rep2 casado). Em ambos os casos é neutro: nunca penaliza a
    # contagem de QF nem é confundido com "comparei e está OK".
    NOT_APPLICABLE = "NOT_APPLICABLE"

    # Dado crítico ausente (NaN) nesta linha para um módulo que É aplicável
    # a esta energia — distinto de NOT_APPLICABLE (aqui o módulo deveria
    # ter medido, só não tem o dado). Nunca confundir com OK (ver
    # plano-de-acao.md, achado C2: dado crítico ausente nunca vira OK).
    INDETERMINATE = "INDETERMINATE"


class QCModule(str, Enum):
    """Identificador de cada módulo QC do núcleo inicial (QC1-QC5)."""

    QC1_INSTRUMENT_STABILITY = "QC1_instrument_stability"
    QC2_COHERENT_SCATTER = "QC2_coherent_scatter"
    QC3_INCOHERENT_SCATTER = "QC3_incoherent_scatter"
    QC4_ROLLING = "QC4_rolling"
    QC5_REPLICATES = "QC5_replicates"


# ============================================================
# QUALITY FLAG
# ============================================================


class QualityFlag(IntEnum):
    """
    Quality Flag final por contagem de estados dos módulos QC1-QC5.

    QF_INDETERMINATE é um estado próprio, nunca confundido com QF0 (OK):
    dado crítico ausente nunca deve virar OK (ver plano-de-acao.md,
    achado C2).
    """

    QF0 = 0
    QF1 = 1
    QF2 = 2
    QF3 = 3
    INDETERMINATE = 9


# Posição visual de cada QF numa escala ordenada (0-3 + indeterminado), para
# uso em gráficos/tabelas sem que INDETERMINATE pareça "mais grave" que QF3.
QF_PLOT_ORDER = {
    QualityFlag.QF0: 0,
    QualityFlag.QF1: 1,
    QualityFlag.QF2: 2,
    QualityFlag.QF3: 3,
    QualityFlag.INDETERMINATE: 4,
}

# ============================================================
# CAUSAS
# ============================================================

# Códigos de causa atribuídos a uma linha quando um módulo não está OK.
CAUSE_THROUGHPUT = "throughput"
CAUSE_ARGON = "argon"
CAUSE_COHERENT = "coherent"
CAUSE_INCOHERENT = "incoherent"
CAUSE_ROLLING = "rolling"
CAUSE_REPLICA = "replica"
CAUSE_MISSING_DATA = "missing_data"

# ============================================================
# VERSÃO DO PIPELINE
# ============================================================

# Identificador da versão do pipeline de QC da V2, registrado em cada linha
# de auditoria (ver qc_audit.py). Não influencia nenhum cálculo científico
# -- é só rastreabilidade (qual versão do código gerou este resultado).
PIPELINE_VERSION = "2.0.0"
