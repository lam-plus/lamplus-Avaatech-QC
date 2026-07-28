# Desenvolvimento — LAM+ Core QC

## O que este app faz

O LAM+ Core QC é um pipeline de Controle de Qualidade para dados gerados pelo
scanner XRF Avaatech. Ele recebe um arquivo Excel exportado pelo scanner e
executa uma série de checagens estatísticas sobre as medidas em réplica
"Rep0" ao longo da profundidade do testemunho (core):

- **QC1–QC3**: z-score robusto (baseado em MAD) sobre Throughput, Rh-Lα e
  Rh-Lα-Inc, para detectar outliers pontuais.
- **QC4 — Rolling QC**: média móvel para detectar deriva local do sinal.
- **QC5 — Réplicas**: RPD (Relative Percent Difference) médio entre réplicas,
  casadas pela posição física de medição (Spectrum + CoreDepth), para um
  conjunto de elementos.
- **QC6 — PCA**: análise de componentes principais sobre os elementos
  selecionados, com distância de Mahalanobis para identificar amostras
  anômalas no espaço multivariado. É sempre calculada como diagnóstico, mas
  por padrão não entra no QI/QF (módulo exploratório, opt-in via checkbox).

A partir desses módulos, o pipeline calcula um **Quality Index (QI)** — uma
combinação ponderada dos scores individuais disponíveis (por padrão, sem
QC6) — e classifica cada medida em um **Quality Flag (QF)**: 0 (OK),
1 (Atenção), 2 (Suspeito), 3 (Rejeitado) ou 9 (Indeterminado, quando falta
dado crítico para avaliar a medição).

O `qc_core.py` contém toda a lógica de cálculo (validação de estrutura do
arquivo, estatísticas, scores e flags) e pode ser usado de forma independente
do frontend. O `qc_avaatech.py` é a interface Streamlit: permite fazer upload
do Excel, visualizar os diagnósticos em gráficos (um por módulo de QC), ver a
tabela de resultados e exportar o resultado final em `.xlsx`.

## Internacionalização (i18n)

**2026-06-28** — as mensagens da interface e as mensagens de validação do
`check_file()` são carregadas a partir de arquivos JSON por idioma
(`locales/pt.json` e `locales/en.json`), via o módulo `i18n.py`. **PT (Português)
é o idioma padrão**; o usuário pode alternar para EN (English) através do
seletor de idioma na sidebar do app Streamlit.

## Empacotamento como executável (PyInstaller)

**2026-06-29** — o app pode ser empacotado como executável standalone
(Windows `.exe` / binário Linux), sem exigir Python ou o `.venv` instalado na
máquina de destino. Todo o sistema de build vive em `installer/`:
`launcher.py` (entry point real — invoca o Streamlit CLI apontando para
`qc_avaatech.py`, já que um script Streamlit não pode ser o entry point do
PyInstaller diretamente), `lamplus_qc.spec` (spec file, cobre as
dependências dinâmicas de `streamlit`/`scipy`/`sklearn`/`matplotlib` e
empacota `locales/`/`assets/`/os módulos do projeto) e `build_exe.py`
(roda o PyInstaller com os parâmetros certos). Instruções completas e
avisos conhecidos em `installer/README_BUILD.md`.

O build foi gerado e testado de ponta a ponta no Windows em 2026-06-29
(executável onefile de ~150MB, servidor Streamlit sobe e responde
normalmente). Ainda não testado no Ubuntu. **O executável gerado nunca é
versionado no repositório** (`installer/dist/`/`installer/build/` estão no
`.gitignore`) — a distribuição é feita via **GitHub Releases**.

---

## Protocolo v4.2 — Análise e Roadmap de Incorporação

**Origem:** protocolo de QC redigido por Igor Oliveira (LAM+), consolidado aqui em 2026-07-28 a partir de `ideas/new-QC.md` — o texto completo (incluindo o apêndice de scripts de referência) foi movido para esta seção; o arquivo solto em `ideas/` foi removido.

### Texto do protocolo (Igor Oliveira — v4.2, Stable)


**Quality Control Protocol for Avaatech XRF Core Scanner Data**

Laboratório de Análise Multiespectral e Inteligência Artificial para Sedimentos (LAM+)  
Universidade Federal Fluminense (UFF)

---

#### 1. Introdução

O XRF Core Scanner permite obter séries geoquímicas contínuas de alta resolução ao longo de testemunhos sedimentares. Apesar da elevada estabilidade do equipamento, diversos fatores físicos e instrumentais podem comprometer a qualidade de medições individuais.

Entre os principais fatores estão:

- superfície irregular do sedimento
- rachaduras
- vazios
- perda de atmosfera de hélio
- baixa estatística de contagem
- problemas locais de aquisição
- baixa reprodutibilidade entre réplicas

O objetivo deste protocolo é identificar automaticamente essas medições potencialmente problemáticas antes da interpretação paleoambiental.

O protocolo foi desenvolvido especificamente para arquivos exportados pelo **Avaatech XRF Core Scanner** utilizados no LAM+.

---

#### 2. Filosofia do protocolo

O princípio central deste protocolo é:

> **Uma composição geoquímica incomum não significa que a medida seja ruim.**

Mudanças ambientais abruptas, sapropéis, cinzas vulcânicas, turbiditos e outros eventos sedimentológicos produzem assinaturas geoquímicas reais.

Essas mudanças **não devem ser confundidas com problemas instrumentais**.

Por esse motivo, o protocolo utiliza exclusivamente parâmetros relacionados ao processo de aquisição do equipamento.

O objetivo é responder apenas:

> **"A medida foi adquirida corretamente?"**

e não

> **"A composição geoquímica parece diferente?"**

---

#### 3. Objetivos

O protocolo procura responder cinco perguntas:

| QC | Pergunta |
|----|----------|
| QC1 | O equipamento apresentou estabilidade durante a aquisição? |
| QC2 | A geometria entre feixe e amostra foi adequada? |
| QC3 | O espalhamento incoerente apresenta comportamento esperado? |
| QC4 | Existem anomalias locais na sequência de aquisição? |
| QC5 | As réplicas apresentam boa reprodutibilidade? |

---

#### 4. Estrutura geral

O protocolo é dividido em cinco módulos independentes:

| QC | Nome | Objetivo |
|----|------|----------|
| QC1 | Instrument Stability | Throughput + Argônio |
| QC2 | Coherent Scatter | Rh-La ou Rh-Ka-Coh |
| QC3 | Incoherent Scatter | Rh-La-Inc ou Rh-Ka-Inc |
| QC4 | Rolling QC | Detecção de anomalias locais |
| QC5 | Replicates | Reprodutibilidade |

Cada módulo retorna apenas um dos seguintes estados:

- **OK**
- **ALERT**
- **CRITICAL**

Nenhum módulo elimina automaticamente uma medida.

---

#### 5. QC1 – Instrument Stability

**Objetivo:** avaliar a estabilidade instrumental durante o escaneamento.

**Parâmetros utilizados:**

| Energia | Parâmetros |
|---------|-----------|
| 10 kV | Throughput, Ar-Ka Area |
| 30 kV | Throughput |
| 50 kV | Throughput |

**Interpretação:**

O Throughput representa o número total de eventos registrados. Valores anormalmente baixos podem indicar perda de intensidade, rachaduras, vazios ou baixa estatística de contagem.

No modo 10 kV também é avaliado o pico de Argônio. O Argônio representa principalmente a qualidade da atmosfera entre tubo, amostra e detector. Valores elevados podem indicar perda de hélio, entrada de ar ou problemas de vedação.

**Classificação:** OK / ALERT / CRITICAL via z-score robusto.

---

#### 6. QC2 – Coherent Scatter

**Objetivo:** avaliar a geometria da medida.

**Variáveis:**

| Energia | Variável |
|---------|----------|
| 10 kV | Rh-La Area |
| 30 kV | Rh-Ka-Coh Area |
| 50 kV | Não aplicável |

**Interpretação:** anomalias podem indicar superfície irregular, mudanças abruptas de densidade ou problemas de posicionamento.

---

#### 7. QC3 – Incoherent Scatter

**Objetivo:** avaliar alterações físicas da interação entre o feixe incidente e a matriz sedimentar.

**Variáveis:**

| Energia | Variável |
|---------|----------|
| 10 kV | Rh-La-Inc Area |
| 30 kV | Rh-Ka-Inc Area |
| 50 kV | Não aplicável |

**Interpretação:** anomalias podem indicar mudanças de matriz, vazios, problemas físicos da superfície ou pequenas falhas de aquisição.

---

#### 8. QC4 – Rolling QC

**Objetivo:** detectar anomalias locais comparando cada ponto com seus vizinhos.

**Variáveis utilizadas:**

- Throughput
- Argônio (quando disponível)
- Coherent Scatter
- Incoherent Scatter

**Procedimento:** para cada variável calcula-se a média móvel (janela = 5 pontos), a diferença entre a medida e a média local, e o robust z-score da diferença.

**Persistência:** um ALERT é emitido apenas quando a anomalia ocorre em pelo menos:

- dois pontos consecutivos, **ou**
- dois pontos dentro de uma janela de três medidas

Essa estratégia reduz falsos positivos produzidos por ruído estatístico.

---

#### 9. QC5 – Replicates

**Objetivo:** avaliar a reprodutibilidade analítica.

**Elementos utilizados:** Al, Si, K, Ca, Ti, Fe  
(Mn não é utilizado devido à elevada variabilidade natural)

**Método:** Relative Percent Difference (RPD)

```
RPD = |max - min| / mean × 100
```

**Classificação:**

| RPD | Resultado |
|-----|-----------|
| < 10% | OK |
| 10–20% | ALERT |
| > 20% | CRITICAL |

---

#### 10. Integração das evidências

Cada QC produz apenas OK / ALERT / CRITICAL. Somente após todos os módulos serem avaliados é calculado o Quality Flag. Nenhuma medida é descartada automaticamente.

---

#### 11. Quality Flags

| QF | Nome | Critério |
|----|------|----------|
| QF0 | Excelente | Nenhum ALERT, nenhum CRITICAL |
| QF1 | Atenção | Apenas um ALERT |
| QF2 | Revisar | 2–3 ALERTs, ou 1 CRITICAL |
| QF3 | Crítico | 2+ CRITICALs, ou 4+ ALERTs |

A medida pode ser utilizada normalmente com QF0 e QF1. QF2 recomenda inspeção visual. QF3 necessita revisão detalhada antes da interpretação.

---

#### 12. Produtos gerados

##### QC_Report.xlsx

O arquivo **não altera a estrutura original** do export do Avaatech. Cada aba (10, 30 e 50 kV) é preservada integralmente. Ao final de cada planilha são adicionadas apenas as seguintes colunas:

| Coluna | Descrição |
|--------|-----------|
| QC1 – Instrument Stability | OK / ALERT / CRITICAL |
| QC2 – Coherent Scatter | OK / ALERT / CRITICAL |
| QC3 – Incoherent Scatter | OK / ALERT / CRITICAL |
| QC4 – Rolling QC | OK / ALERT |
| QC5 – Replicates | OK / ALERT / CRITICAL |
| Primary Reason | Principal causa do flag |
| Supporting Evidence | Evidências adicionais |
| Quality Flag | QF0–QF3 |
| Review | YES / NO |

`Review = YES` para QF2 e QF3. Aba extra `Flagged_Intervals` com coloração automática (verde/amarelo/vermelho).

##### QC_Summary.txt

Resumo automático contendo: arquivo analisado, energia, número de medições, distribuição dos Quality Flags, resumo por módulo, lista das profundidades QF2/QF3, motivo principal, evidências secundárias, conclusão automática.

---

#### 13. Interpretação

O protocolo **não elimina dados**. Ele apenas recomenda inspeção adicional. A decisão final deve considerar conjuntamente:

- Quality Flag
- fotografia do testemunho
- imagem RGB
- descrição sedimentológica
- experiência do pesquisador

---

#### 14. Limitações

Os limiares estatísticos adotados representam uma primeira implementação operacional e deverão ser calibrados com um conjunto maior de testemunhos de boa qualidade. O protocolo não substitui a interpretação geológica nem deve ser utilizado para rejeição automática de dados.

---

#### 15. Conclusão

O **LAM+ XRF CoreQC v4.2** padroniza a avaliação da qualidade de dados de XRF Core Scanner por meio de cinco módulos independentes focados exclusivamente na aquisição instrumental. O protocolo foi concebido para reduzir falsos positivos, preservar a integridade dos dados originais e fornecer ao pesquisador informações objetivas sobre quais intervalos merecem inspeção adicional.

---

#### Apêndice — Scripts (v4.2)

##### Estrutura de módulos

```
LAM_CoreQC/
├── config.py
├── main.py
├── io_module.py
├── qc.py
├── reports.py
├── replicates.py
├── utils.py
└── README.md
```

---

##### config.py

```python
"""
LAM+ XRF CoreQC v4.2
Configuration File
Author: Igor Oliveira
"""

# Depth columns (priority order)
DEPTH_COLUMNS = [
    "CompositeDepth (mm)",
    "CompositeDepth",
    "CoreDepth",
    "Core Depth"
]

# Replicate
MAIN_REPLICATE = "Rep0"
REPLICATE_COLUMN = "Replicate Nr Count"

# Rolling QC
ROLLING_WINDOW = 5
ROLLING_MIN_POINTS = 2
ROLLING_ALERT_Z = 4.0

# Z-score limits
WARNING_Z = 2.5
CRITICAL_Z = 3.5

# Replicate QC thresholds
REPLICA_WARNING = 10.0
REPLICA_CRITICAL = 20.0

# Replicate elements (Mn excluded — high natural variability)
REPLICA_ELEMENTS = [
    "Al-Ka Area",
    "Si-Ka Area",
    "K-Ka Area",
    "Ca-Ka Area",
    "Ti-Ka Area",
    "Fe-Ka Area"
]

# Energy configuration
ENERGY_PARAMETERS = {
    "10kV": {
        "throughput": "Throughput",
        "argon": "Ar-Ka Area",
        "coherent": "Rh-La Area",
        "incoherent": "Rh-La-Inc Area"
    },
    "30kV": {
        "throughput": "Throughput",
        "argon": None,
        "coherent": "Rh-Ka-Coh Area",
        "incoherent": "Rh-Ka-Inc Area"
    },
    "50kV": {
        "throughput": "Throughput",
        "argon": None,
        "coherent": None,
        "incoherent": None
    }
}

# QC states
QC_OK = "OK"
QC_WARNING = "WARNING"
QC_CRITICAL = "CRITICAL"

# Quality Flags
QF0 = "QF0"
QF1 = "QF1"
QF2 = "QF2"
QF3 = "QF3"

# Review
REVIEW_YES = "YES"
REVIEW_NO = "NO"

# Output files
OUTPUT_EXCEL = "QC_Report.xlsx"
OUTPUT_SUMMARY = "QC_Summary.txt"
```

---

##### main.py

```python
"""
LAM+ XRF CoreQC
main.py
"""

from io_module import read_workbook
from qc import run_quality_control
from reports import export_results

INPUT_FILE = "Dados.xlsx"

datasets = read_workbook(INPUT_FILE)
results = run_quality_control(datasets)
export_results(results)

print("Finished.")
```

---

##### io_module.py

```python
"""
LAM+ XRF CoreQC v4.2
Input / Output Module

Responsible for:
- Opening the Excel workbook
- Reading every sheet
- Detecting X-ray energy
- Detecting depth column
- Selecting Rep0
- Returning standardized datasets
"""

import pandas as pd
from config import *


def detect_depth_column(df):
    """Detect depth column from priority list."""
    for col in DEPTH_COLUMNS:
        if col in df.columns:
            return col
    raise Exception("Depth column not found.")


def detect_energy(sheet_name):
    """Detect energy from sheet name."""
    name = sheet_name.lower()
    if "10" in name:
        return "10kV"
    elif "30" in name:
        return "30kV"
    elif "50" in name:
        return "50kV"
    else:
        raise Exception(f"Unknown sheet: {sheet_name}")


def select_main_replicate(df):
    """Keep only Rep0 measurements."""
    if REPLICATE_COLUMN not in df.columns:
        return df.copy()
    return df[df[REPLICATE_COLUMN] == MAIN_REPLICATE].copy()


def read_sheet(file_name, sheet_name):
    """Read one worksheet."""
    df = pd.read_excel(file_name, sheet_name=sheet_name)
    depth = detect_depth_column(df)
    energy = detect_energy(sheet_name)
    rep0 = select_main_replicate(df)
    rep0 = rep0.sort_values(depth)
    return {
        "sheet_name": sheet_name,
        "energy": energy,
        "depth_column": depth,
        "raw_data": df,
        "rep0": rep0
    }


def read_workbook(file_name):
    """Read complete workbook."""
    xls = pd.ExcelFile(file_name)
    datasets = []
    for sheet in xls.sheet_names:
        try:
            data = read_sheet(file_name, sheet)
            datasets.append(data)
        except Exception as e:
            print(f"Skipping {sheet}: {e}")
    return datasets
```

---

##### qc.py

```python
"""
LAM+ XRF CoreQC v4.2
Quality Control Module
"""

import numpy as np
import pandas as pd
from config import *
from replicates import calculate_replica_qc


def robust_z(x):
    x = np.asarray(x, dtype=float)
    median = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - median))
    if mad == 0:
        return np.zeros(len(x))
    return 0.6745 * (x - median) / mad


def rolling_qc(series):
    rolling = series.rolling(
        window=ROLLING_WINDOW,
        center=True,
        min_periods=1
    ).mean()
    delta = series - rolling
    return np.abs(robust_z(delta))


def classify_z(z):
    state = []
    for value in z:
        if np.isnan(value):
            state.append(QC_OK)
        elif value >= CRITICAL_Z:
            state.append(QC_CRITICAL)
        elif value >= WARNING_Z:
            state.append(QC_WARNING)
        else:
            state.append(QC_OK)
    return state


def classify_rolling(z):
    state = []
    for value in z:
        if np.isnan(value):
            state.append(QC_OK)
        elif value >= ROLLING_ALERT_Z:
            state.append(QC_WARNING)
        else:
            state.append(QC_OK)
    return state


def merge_states(states):
    alerts = []
    criticals = []
    for name, state in states.items():
        if state == QC_WARNING:
            alerts.append(name)
        elif state == QC_CRITICAL:
            criticals.append(name)
    return alerts, criticals


def evaluate_flag(alerts, criticals):
    if len(alerts) == 0 and len(criticals) == 0:
        return QF0
    elif len(alerts) == 1 and len(criticals) == 0:
        return QF1
    elif len(criticals) >= 2 or len(alerts) >= 4:
        return QF3
    else:
        return QF2


def run_quality_control(datasets):
    results = []
    for ds in datasets:
        df = ds["rep0"].copy()
        raw = ds["raw_data"]
        energy = ds["energy"]
        depth = ds["depth_column"]
        cfg = ENERGY_PARAMETERS[energy]

        # QC1 — Throughput + Argon
        tp_state = classify_z(np.abs(robust_z(df[cfg["throughput"]])))
        if cfg["argon"] is not None and cfg["argon"] in df.columns:
            ar_state = classify_z(np.abs(robust_z(df[cfg["argon"]])))
        else:
            ar_state = [QC_OK] * len(df)

        # QC2 — Coherent Scatter
        if cfg["coherent"] is not None and cfg["coherent"] in df.columns:
            coh_state = classify_z(np.abs(robust_z(df[cfg["coherent"]])))
        else:
            coh_state = [QC_OK] * len(df)

        # QC3 — Incoherent Scatter
        if cfg["incoherent"] is not None and cfg["incoherent"] in df.columns:
            inc_state = classify_z(np.abs(robust_z(df[cfg["incoherent"]])))
        else:
            inc_state = [QC_OK] * len(df)

        # QC4 — Rolling QC (max across variables)
        rolling = np.zeros(len(df))
        for var in [cfg["throughput"], cfg["argon"], cfg["coherent"], cfg["incoherent"]]:
            if var is None or var not in df.columns:
                continue
            rolling = np.maximum(rolling, rolling_qc(df[var]))
        rolling_state = classify_rolling(rolling)

        # QC1 combined (Throughput + Argon)
        qc1 = []
        for a, b in zip(tp_state, ar_state):
            if QC_CRITICAL in [a, b]:
                qc1.append(QC_CRITICAL)
            elif QC_WARNING in [a, b]:
                qc1.append(QC_WARNING)
            else:
                qc1.append(QC_OK)

        # QC5 — Replicates
        replica_result = calculate_replica_qc(raw, df, depth)
        replica_state = replica_result["state"]

        # Integration
        primary = []
        support = []
        flags = []
        review = []
        qc1_out = []
        qc2_out = []
        qc3_out = []
        qc4_out = []
        qc5_out = []

        for i in range(len(df)):
            states = {
                "Instrument Stability": qc1[i],
                "Coherent Scatter": coh_state[i],
                "Incoherent Scatter": inc_state[i],
                "Rolling QC": rolling_state[i],
                "Replicates": replica_state[i]
            }
            alerts, criticals = merge_states(states)
            qf = evaluate_flag(alerts, criticals)
            flags.append(qf)
            review.append(REVIEW_YES if qf in [QF2, QF3] else REVIEW_NO)

            if len(criticals) > 0:
                primary.append(criticals[0])
                support.append(", ".join(alerts))
            elif len(alerts) > 0:
                primary.append(alerts[0])
                support.append(", ".join(alerts[1:]))
            else:
                primary.append("")
                support.append("")

            qc1_out.append(qc1[i])
            qc2_out.append(coh_state[i])
            qc3_out.append(inc_state[i])
            qc4_out.append(rolling_state[i])
            qc5_out.append(replica_state[i])

        df["QC1 - Instrument"] = qc1_out
        df["QC2 - Coherent"] = qc2_out
        df["QC3 - Incoherent"] = qc3_out
        df["QC4 - Rolling"] = qc4_out
        df["QC5 - Replicates"] = qc5_out
        df["Primary Reason"] = primary
        df["Supporting Evidence"] = support
        df["Quality Flag"] = flags
        df["Review"] = review

        ds["output"] = df
        results.append(ds)

    return results
```

---

##### replicates.py

```python
"""
LAM+ XRF CoreQC
Replicate QC Module
"""

import numpy as np
from config import *


def rpd(values):
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if len(values) < 2:
        return np.nan
    mean = np.mean(values)
    if mean == 0:
        return np.nan
    return np.abs(values.max() - values.min()) / mean * 100


def evaluate_depth(subset):
    element_rpd = {}
    for element in REPLICA_ELEMENTS:
        if element not in subset.columns:
            continue
        value = rpd(subset[element])
        element_rpd[element] = value

    if len(element_rpd) == 0:
        return {"status": QC_OK, "average_rpd": np.nan,
                "worst_element": "", "worst_rpd": np.nan}

    values = [v for v in element_rpd.values() if not np.isnan(v)]
    if len(values) == 0:
        return {"status": QC_OK, "average_rpd": np.nan,
                "worst_element": "", "worst_rpd": np.nan}

    average_rpd = np.mean(values)
    worst_element = max(element_rpd, key=element_rpd.get)
    worst_rpd = element_rpd[worst_element]

    if worst_rpd >= REPLICA_CRITICAL:
        status = QC_CRITICAL
    elif worst_rpd >= REPLICA_WARNING:
        status = QC_WARNING
    else:
        status = QC_OK

    return {"status": status, "average_rpd": average_rpd,
            "worst_element": worst_element, "worst_rpd": worst_rpd}


def calculate_replica_qc(raw, rep0, depth_column):
    states = []
    average = []
    worst_element = []
    worst_rpd = []

    for depth in rep0[depth_column]:
        subset = raw[raw[depth_column] == depth]
        if len(subset) < 2:
            states.append(QC_OK)
            average.append(np.nan)
            worst_element.append("")
            worst_rpd.append(np.nan)
            continue

        result = evaluate_depth(subset)
        states.append(result["status"])
        average.append(result["average_rpd"])
        worst_element.append(result["worst_element"])
        worst_rpd.append(result["worst_rpd"])

    return {
        "state": states,
        "average_rpd": average,
        "worst_element": worst_element,
        "worst_rpd": worst_rpd
    }
```

---

##### reports.py

```python
"""
LAM+ XRF CoreQC
Reports Module

Exports:
- QC_Report.xlsx
- QC_Summary.txt
"""

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import PatternFill
from config import *

GREEN = PatternFill(fill_type="solid", start_color="C6EFCE")
YELLOW = PatternFill(fill_type="solid", start_color="FFF2CC")
RED = PatternFill(fill_type="solid", start_color="F4CCCC")


def color(cell):
    if cell.value in ["OK", QF0, "NO"]:
        cell.fill = GREEN
    elif cell.value in ["WARNING", QF1]:
        cell.fill = YELLOW
    elif cell.value in ["CRITICAL", QF2, QF3, "YES"]:
        cell.fill = RED


def export_excel(results):
    writer = pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl")
    flagged = []

    for ds in results:
        raw = ds["raw_data"].copy()
        out = ds["output"]
        depth = ds["depth_column"]

        cols = [
            "QC1 - Instrument", "QC2 - Coherent", "QC3 - Incoherent",
            "QC4 - Rolling", "QC5 - Replicates",
            "Replica Average RPD (%)", "Replica Worst Element",
            "Replica Worst RPD (%)", "Primary Reason",
            "Supporting Evidence", "Quality Flag", "Review"
        ]
        for c in cols:
            raw[c] = ""

        for _, r in out.iterrows():
            idx = raw.index[raw[depth] == r[depth]][0]
            for c in cols:
                if c in r:
                    raw.loc[idx, c] = r[c]

        raw.to_excel(writer, sheet_name=ds["sheet_name"], index=False)
        flagged.append(out[out["Review"] == "YES"])

    pd.concat(flagged).to_excel(writer, sheet_name="Flagged_Intervals", index=False)
    writer.close()

    wb = load_workbook(OUTPUT_EXCEL)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                color(cell)
    wb.save(OUTPUT_EXCEL)


def export_summary(results):
    with open(OUTPUT_SUMMARY, "w", encoding="utf-8") as f:
        f.write("LAM+ XRF CoreQC v4.2\n\n")

        for ds in results:
            out = ds["output"]
            f.write("=" * 60 + "\n")
            f.write(ds["sheet_name"] + "\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Measurements : {len(out)}\n\n")
            f.write("Quality Flags\n\n")

            for qf in [QF0, QF1, QF2, QF3]:
                n = (out["Quality Flag"] == qf).sum()
                p = n / len(out) * 100
                f.write(f"{qf}: {n} ({p:.1f}%)\n")
            f.write("\n")

            modules = [
                "QC1 - Instrument", "QC2 - Coherent",
                "QC3 - Incoherent", "QC4 - Rolling", "QC5 - Replicates"
            ]
            f.write("QC Modules\n\n")
            for m in modules:
                warn = (out[m] == "WARNING").sum()
                crit = (out[m] == "CRITICAL").sum()
                f.write(f"{m}\n")
                f.write(f"WARNING : {warn}\n")
                f.write(f"CRITICAL: {crit}\n\n")

            flagged = out[out["Review"] == "YES"]
            if len(flagged) > 0:
                f.write("Intervals requiring review\n\n")
                for _, r in flagged.iterrows():
                    f.write(f"{r[ds['depth_column']]} mm | ")
                    f.write(f"{r['Quality Flag']} | ")
                    f.write(f"{r['Primary Reason']}")
                    if r["Supporting Evidence"] != "":
                        f.write(f" ({r['Supporting Evidence']})")
                    f.write("\n")
            f.write("\n\n")


def export_results(results):
    export_excel(results)
    export_summary(results)
    print()
    print("QC_Report.xlsx exported.")
    print("QC_Summary.txt exported.")
```

### Análise comparativa e classificação de incorporação (2026-07-28)

Comparação entre o protocolo acima e a implementação atual (`qc_core.py`/`qc_avaatech.py`), feita item a item. Cada diferença foi classificada como **INCORPORAR** (funcionalidade nova a trazer), **MODIFICAR** (lógica existente a alterar), **MANTER** (o atual já é melhor/complementar) ou **DESCARTAR** (o v4.2 contradiz decisão já tomada).

**Resumo executivo:** o v4.2 é mais rigoroso na filosofia de aquisição (5 módulos focados só em "a medida foi bem adquirida", nunca em composição geoquímica) e traz elementos genuinamente novos (Argônio, multi-energia, persistência temporal no rolling, modo de QF por contagem). Mas também **reintroduz dois bugs já corrigidos** no código atual (achados C1 e C2 do `TODO.md`) e não tem nada de i18n, PCA diagnóstica, seletor de profundidade exibida ou explicabilidade de causa por linha — tudo isso já existe e é melhor no código atual.

#### 1. Estrutura geral / arquitetura de arquivos

**DESCARTAR** — o layout `config.py/main.py/io_module.py/qc.py/reports.py/replicates.py` do apêndice é um script batch standalone (lê `Dados.xlsx`, escreve `QC_Report.xlsx`/`QC_Summary.txt`, sem UI). Contradiz a decisão já documentada em `CLAUDE.md`: `qc_core.py` como lib pura + `qc_avaatech.py` como único frontend Streamlit. Não vale portar a separação de arquivos — só extrair a *lógica* de dentro dela.

**MANTER** — i18n completo (PT default + EN via `locales/*.json`), PCA/Mahalanobis como módulo diagnóstico opcional, seletor `CompositeDepth`/`CoreDepth` para exibição, geração de PDF com intervalos + causas traduzidas. Nada disso existe no v4.2 (100% em inglês hardcoded, sem PCA).

#### 2. QC1 — Instrument Stability (Throughput + Argônio)

**INCORPORAR** — v4.2 combina Throughput + `Ar-Ka Area` (pico de Argônio, indicador de perda de hélio/vedação) em 10 kV. O atual (`qc_throughput`, `qc_core.py:214`) usa só Throughput. A coluna `Ar-Ka Area` existe de fato no arquivo de exemplo (confirmado lendo o Excel) e está sendo desperdiçada.

#### 3. QC2/QC3 — Coherent/Incoherent Scatter

**MANTER** — mapeiam 1:1 para `qc_rh_la`/`qc_rh_la_inc` atuais. A nomenclatura conceitual do v4.2 é mais clara cientificamente — vale trazer só como *label* de exibição (chave i18n), sem mudar a lógica.

**INCORPORAR (condicional)** — v4.2 varia a variável por energia (`Rh-Ka-Coh`/`Rh-Ka-Inc` em 30 kV, ausente em 50 kV). Só relevante se o laboratório de fato gerar arquivos multi-energia (ver item 6).

#### 4. QC4 — Rolling QC

**MODIFICAR (discutir antes)** — duas diferenças reais frente a `qc_rolling`/`compute_scores` (`qc_core.py:235`, `qc_core.py:343-348`):

1. **Persistência temporal**: v4.2 só emite ALERT quando a anomalia aparece em ≥2 pontos consecutivos ou 2 pontos numa janela de 3 — reduz falsos positivos de ruído estatístico pontual. O atual dispara com um único ponto acima do z-threshold. Tensiona com decisão já tomada (item 1.5 do TODO): flag pontual único é intencional ("defesa em profundidade"), só explicado via `is_pointwise_flag`/`Pointwise_Flag_Note` em vez de suprimido. **Precisa decisão do time.**
2. v4.2 inclui Argônio no conjunto de variáveis do rolling — consistente com a incorporação do Argônio no QC1.

**DESCARTAR (parcial)** — v4.2 sempre combina as variáveis via máximo (equivalente a `combine_rolling_vars=True` fixo, sem opção). Contradiz a decisão de 2026-06-28 (item 4.1 do TODO) de que Rh-Lα-Inc sozinho é o default. Manter o comportamento atual (com Argônio como quarta variável opcional, se incorporado).

#### 5. QC5 — Réplicas

**DESCARTAR (crítico)** — `replicates.py` do v4.2 casa réplicas por **igualdade exata de profundidade**. É exatamente o bug do achado C1, já corrigido (`REPLICATE_KEY_COLS = ["Spectrum", "CoreDepth"]`, `qc_core.py:246-269`): `CompositeDepth (mm)` fica nulo em Rep1/Rep2 no arquivo real. **Não portar essa parte do v4.2.**

**INCORPORAR** — `rpd()` do v4.2 trata `mean == 0` retornando `NaN` explicitamente. É a correção do item 1.1, ainda aberto no `TODO.md` (`calculate_rpd` atual gera `inf` em vez de `NaN`, causando `RuntimeWarning`). Correção pequena e direta.

**MODIFICAR (a discutir)** — v4.2 usa thresholds discretos de RPD (<10% OK, 10–20% ALERT, >20% CRITICAL) em vez da fórmula contínua atual (`100 - Mean_RPD*4`). Filosofias diferentes — só relevante se o modo de QF por contagem (item 7) for adotado.

#### 6. Estrutura multi-energia (10/30/50 kV) e detecção automática

**Em aberto, não classificável ainda** — todo o `io_module.py` do v4.2 assume um workbook com múltiplas abas nomeadas por energia e parâmetros diferentes por energia. O arquivo de exemplo atual só tem uma aba (`10kv`), e `qc_avaatech.py:190` lê com `pd.read_excel(uploaded)` sem `sheet_name` — pega só a primeira aba silenciosamente (item 3.1 do TODO). **Pergunta para o time:** os arquivos reais do LAM+ chegam com múltiplas abas de energia, ou é cenário futuro/outro equipamento? Se sim, é mudança arquitetural grande, não ajuste pontual.

#### 7. Quality Flag — filosofia de agregação

A diferença mais profunda entre os dois documentos.

- **Atual**: QI contínuo ponderado (`QI_WEIGHTS`) + critérios pontuais de z-score/Mahalanobis sobrepostos (`compute_flags`, `qc_core.py:401-460`). Um módulo muito bom pode compensar outro ruim.
- **v4.2**: cada módulo vira um estado discreto (OK/ALERT/CRITICAL) e o QF final é contagem de estados (`evaluate_flag`): QF0 sem alerta, QF1 = 1 alerta, QF2 = 2-3 alertas ou 1 crítico, QF3 = 2+ críticos ou 4+ alertas. Não compensatório.

**INCORPORAR** — é literalmente o item 8.7, já registrado no `TODO.md` como funcionalidade planejada ("modo alternativo de QF por contagem de módulos reprovados vs. QI ponderado"), e o v4.2 entrega uma especificação pronta. Implementar como segundo modo **opt-in** (o QI ponderado continua default).

**DESCARTAR (crítico)** — `classify_z`/`classify_rolling` do v4.2 tratam `NaN` como `QC_OK` explicitamente. É exatamente o bug do achado C2, já corrigido (`QF_INDETERMINATE=9`, `is_indeterminate` calculado antes do loop, `qc_core.py:420`). Se o modo de contagem for incorporado, a lógica de NaN precisa produzir indeterminado, nunca OK — não portar essa parte literalmente.

#### 8. Produtos de saída (Excel/relatório)

**INCORPORAR** — preenchimento de cor por célula no Excel (verde/amarelo/vermelho via `openpyxl.PatternFill`) é melhoria de UX simples, sem dependência nova (openpyxl já usado em `to_excel_bytes`, `qc_avaatech.py:120`).

**MANTER** — o relatório atual (PDF com página de intervalos problemáticos, causas traduzidas, ícone de flag pontual, nota de rodapé — `report_pdf.py`) é estruturalmente mais rico que o `QC_Summary.txt` simples do v4.2. Não vale substituir; no máximo, gerar um `.txt`/resumo simples como complemento rápido do PDF.

**MODIFICAR (a discutir)** — v4.2 preserva o `raw_data` completo (todas as réplicas Rep0/Rep1/Rep2) no Excel de saída, anotando QC só nas linhas Rep0. O `.xlsx` atual exporta só o subconjunto `rep0` filtrado. Pode valer a pena manter as réplicas brutas no export para rastreabilidade — confirmar se é desejado.

#### Tabela-síntese

| # | Item | Classificação |
|---|------|------|
| 1 | Layout de arquivos (config/main/io_module/qc/reports/replicates) | **DESCARTAR** |
| 2 | i18n, PCA diagnóstica, seletor de profundidade, PDF de intervalos | **MANTER** |
| 3 | Argônio (Ar-Ka Area) em QC1 | **INCORPORAR** |
| 4 | Nomenclatura "Coherent/Incoherent Scatter" como label | **INCORPORAR (leve)** |
| 5 | Persistência temporal no QC4 (2 pontos consecutivos) | **MODIFICAR — discutir antes** (tensiona com decisão já tomada sobre flag pontual único) |
| 6 | Combinar sempre as variáveis no rolling (sem opt-in) | **DESCARTAR** |
| 7 | Casamento de réplica por igualdade exata de profundidade | **DESCARTAR (crítico — regride achado C1)** |
| 8 | `rpd()` com `mean==0` → NaN | **INCORPORAR (correção direta do TODO 1.1)** |
| 9 | Thresholds discretos de RPD (10%/20%) | **MODIFICAR — só se item 12 for adotado** |
| 10 | Estrutura multi-energia (abas 10/30/50 kV) | **EM ABERTO — pergunta para o time** |
| 11 | NaN → sempre "OK" nos estados discretos | **DESCARTAR (crítico — regride achado C2)** |
| 12 | QF por contagem de módulos reprovados | **INCORPORAR (é o item 8.7 do TODO, já planejado)** |
| 13 | Preenchimento de cor no Excel exportado | **INCORPORAR** |
| 14 | QC_Summary.txt | **MANTER PDF atual; TXT como complemento opcional** |
| 15 | Exportar réplicas brutas junto no `.xlsx` | **MODIFICAR — confirmar com usuário** |

**Ordem de implementação sugerida:** ver `TODO.md`, seção "Protocolo v4.2 — itens priorizados de incorporação".
