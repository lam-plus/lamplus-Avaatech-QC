"""
LAM+ Core QC — report_pdf.py
Geração de relatórios PDF a partir do resultado de qc_core.run_qc().

Uso:
    from report_pdf import detect_intervals, build_problem_intervals_page
"""

import matplotlib.pyplot as plt

from qc_core import (
    CORE_DEPTH_COL,
    DEPTH_COL,
    QF_PLOT_ORDER,
    QI_THRESHOLD_OK,
    format_causes,
    is_pointwise_flag,
)

# Nomes curtos (técnicos, não traduzidos) usados nos cabeçalhos da tabela de
# intervalos, para indicar qual coluna de profundidade está sendo exibida.
_DEPTH_COL_SHORT_NAMES = {DEPTH_COL: "CompositeDepth", CORE_DEPTH_COL: "CoreDepth"}

# ============================================================
# INTERVALOS PROBLEMÁTICOS
# ============================================================

def detect_intervals(rep0, min_gap=20, depth_col=DEPTH_COL):
    """
    Agrupa medidas consecutivas com QF >= 2 (inclui QF_INDETERMINATE) em
    intervalos contíguos de profundidade, tolerando gaps de até min_gap mm
    entre pontos do mesmo cluster.

    Args:
        rep0: DataFrame já processado por run_qc (precisa de DEPTH_COL, QF,
            QF_Causes).
        min_gap: distância máxima (mm) entre dois pontos problemáticos
            consecutivos para ainda serem considerados o mesmo intervalo.
        depth_col: coluna usada para o tamanho do gap e para os valores
            depth_start/depth_end reportados — DEPTH_COL (composta, padrão)
            ou CORE_DEPTH_COL (local, reinicia a cada seção do testemunho).
            Puramente de exibição: a ordem de varredura dos pontos usa
            sempre DEPTH_COL (contínua/monotônica), nunca depth_col — usar
            CORE_DEPTH_COL para ordenar misturaria seções diferentes do
            testemunho, já que ali a profundidade reinicia a cada tubo.
            Em testemunhos com múltiplas seções, um intervalo que cruze uma
            transição de seção pode reportar depth_end < depth_start quando
            depth_col=CORE_DEPTH_COL — limitação conhecida, aceita por ser
            puramente de exibição (não afeta o agrupamento em si).

    Retorna:
        list[dict] — um dict por intervalo, com:
            depth_start        : profundidade inicial (mm), na coluna depth_col
            depth_end          : profundidade final (mm), na coluna depth_col
            n_points           : número de medidas no intervalo
            qf_max             : maior QF presente no intervalo
            causes             : set[str] com os códigos de causa (CAUSE_*)
                                 únicos presentes em qualquer medida do
                                 intervalo
            has_pointwise_flag : True se alguma medida do intervalo foi
                                 flagrada por um critério pontual (z-score
                                 ou Mahalanobis) com QI ainda >= QI_THRESHOLD_OK
                                 (ver qc_core.is_pointwise_flag) — ou seja, o
                                 QF ali não reflete o QI agregado.
    """
    # Sempre ordena E decide os gaps pela profundidade canônica do pipeline
    # (contínua/monotônica) — nunca por depth_col, que pode reiniciar a cada
    # seção (CORE_DEPTH_COL) e mascarar transições de seção como "gap
    # pequeno" (a diferença ficaria negativa, nunca > min_gap). depth_col só
    # é usado para os valores depth_start/depth_end efetivamente exibidos.
    problem = rep0[rep0["QF"] >= 2].sort_values(DEPTH_COL)
    if problem.empty:
        return []

    true_depths = problem[DEPTH_COL].to_numpy()
    display_depths = problem[depth_col].to_numpy()
    qfs = problem["QF"].to_numpy()
    causes_raw = problem["QF_Causes"].fillna("").to_numpy()
    pointwise = is_pointwise_flag(problem).to_numpy()

    intervals = []
    cluster_start = 0
    n = len(true_depths)
    for i in range(1, n + 1):
        gap_exceeded = i < n and (true_depths[i] - true_depths[i - 1] > min_gap)
        if i == n or gap_exceeded:
            cluster_causes = set()
            for c in causes_raw[cluster_start:i]:
                if c:
                    cluster_causes.update(c.split(";"))
            intervals.append({
                "depth_start": float(display_depths[cluster_start]),
                "depth_end": float(display_depths[i - 1]),
                "n_points": int(i - cluster_start),
                "qf_max": int(qfs[cluster_start:i].max()),
                "causes": cluster_causes,
                "has_pointwise_flag": bool(pointwise[cluster_start:i].any()),
            })
            cluster_start = i

    return intervals


# ============================================================
# PÁGINA DE PDF
# ============================================================

def _format_qf_label(qf, T):
    """Traduz um código QF para o label de exibição (mesma ordem/labels do gráfico QI/QF)."""
    labels = T["plot_qf_labels"]
    pos = QF_PLOT_ORDER.get(qf)
    if pos is None or pos >= len(labels):
        return str(qf)
    return labels[pos]


def build_problem_intervals_page(intervals, T, depth_col=DEPTH_COL):
    """
    Constrói uma página (matplotlib Figure) listando os intervalos
    problemáticos detectados por detect_intervals, um por linha, com
    profundidade início/fim, nº de medidas, QF máximo e causas agregadas.

    depth_col indica qual coluna de profundidade os valores depth_start/
    depth_end de "intervals" representam (apenas para rotular o cabeçalho
    da tabela — passe o mesmo depth_col usado em detect_intervals).

    Intervalos com has_pointwise_flag=True recebem um ícone "⚠" junto ao QF
    máximo, e a página ganha uma nota de rodapé explicando que o flag, ali,
    veio de um critério pontual (z-score/Mahalanobis) e não do QI agregado.
    """
    fig, ax = plt.subplots(figsize=(10, max(2, 0.5 * len(intervals) + 1.5)))
    ax.axis("off")
    ax.set_title(T["report_intervals_title"], fontsize=14, fontweight="bold", loc="left")

    if not intervals:
        ax.text(0, 0.8, T["report_intervals_empty"], fontsize=11)
        return fig

    depth_label = _DEPTH_COL_SHORT_NAMES.get(depth_col, depth_col)
    columns = [
        T["report_intervals_depth_start"].format(label=depth_label),
        T["report_intervals_depth_end"].format(label=depth_label),
        T["report_intervals_n_points"],
        T["report_intervals_qf_max"],
        T["report_intervals_causes"],
    ]

    rows = []
    any_pointwise = False
    for iv in intervals:
        qf_label = _format_qf_label(iv["qf_max"], T)
        if iv["has_pointwise_flag"]:
            qf_label += " ⚠"
            any_pointwise = True
        rows.append([
            f"{iv['depth_start']:.1f}",
            f"{iv['depth_end']:.1f}",
            str(iv["n_points"]),
            qf_label,
            format_causes(iv["causes"], T),
        ])

    table = ax.table(cellText=rows, colLabels=columns, loc="upper left", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.auto_set_column_width(col=list(range(len(columns))))

    if any_pointwise:
        fig.text(
            0.02, 0.02,
            T["pdf_pointwise_footnote"].format(threshold=QI_THRESHOLD_OK),
            fontsize=8, style="italic", color="#555555",
        )

    fig.tight_layout()
    return fig
