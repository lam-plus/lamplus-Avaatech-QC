# Desenvolvimento — LAM+ Core QC

## O que este app faz

O LAM+ Core QC é um pipeline de Controle de Qualidade para dados gerados pelo
scanner XRF Avaatech. Ele recebe um arquivo Excel exportado pelo scanner —
uma única aba (10 kV) ou um **workbook multi-energia** (abas separadas 10 kV/
30 kV/50 kV, detectadas automaticamente pelo nome — ver "Estrutura
multi-energia" abaixo) — e executa uma série de checagens estatísticas sobre
as medidas em réplica "Rep0" ao longo da profundidade do testemunho (core):

- **QC1 — Instrument Stability**: z-score robusto do Throughput, combinado
  com o pico de Argônio (Ar-Kα) quando presente (só existe em modo 10 kV) —
  usa o pior dos dois z-scores, linha a linha.
- **QC2/QC3 — Coherent/Incoherent Scatter**: z-score robusto pontual sobre o
  espalhamento coerente/incoerente da energia (Rh-Lα/Rh-Lα-Inc em 10 kV,
  Rh-Kα-Coh/Rh-Kα-Inc em 30 kV; não medidos em 50 kV).
- **QC4 — Rolling QC**: média móvel para detectar deriva local do sinal, na
  variável incoerente da energia por padrão (opt-in para combinar todas as
  variáveis disponíveis). Opcionalmente exige persistência temporal (≥2
  pontos consecutivos ou numa janela de 3) antes de considerar a anomalia,
  em vez de reagir a um único ponto isolado (opt-in, default desligado).
- **QC5 — Réplicas**: RPD (Relative Percent Difference) médio entre réplicas,
  casadas pela posição física de medição (Spectrum + CoreDepth), para um
  conjunto de elementos.
- **QC6 — PCA**: análise de componentes principais sobre os elementos
  selecionados, com distância de Mahalanobis para identificar amostras
  anômalas no espaço multivariado. É sempre calculada como diagnóstico, mas
  por padrão não entra no QI/QF (módulo exploratório, opt-in via checkbox).

Um módulo que a energia da aba não mede (ex. QC2/QC3 em 50 kV) recebe nota
neutra e tem seu peso excluído do QI para aquela aba, em vez de ser tratado
como dado faltante.

A partir desses módulos, o pipeline calcula um **Quality Index (QI)** — uma
combinação ponderada dos scores individuais disponíveis (por padrão, sem
QC6) — e classifica cada medida em um **Quality Flag (QF)**: 0 (OK),
1 (Atenção), 2 (Suspeito), 3 (Rejeitado) ou 9 (Indeterminado, quando falta
dado crítico para avaliar a medição). Duas filosofias de atribuição de QF
estão disponíveis (opt-in via checkbox): o modo QI ponderado (default,
compensatório) e o modo de contagem de módulos reprovados do protocolo v4.2
(não compensatório — ver seção "Protocolo v4.2" abaixo).

O `qc_core.py` contém toda a lógica de cálculo (validação de estrutura do
arquivo, estatísticas, scores e flags) e pode ser usado de forma independente
do frontend. O `qc_avaatech.py` é a interface Streamlit: permite fazer upload
do Excel (uma ou várias abas), visualizar os diagnósticos em gráficos (um por
módulo de QC, por aba/energia), ver a tabela de resultados e exportar o
resultado final em `.xlsx` (uma aba por energia processada, com coloração
condicional verde/amarelo/vermelho nas colunas de QC adicionadas).

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

✅ **INCORPORADO em 2026-07-28** (`TODO.md`, seção 9, item b) — `qc_throughput` agora combina Throughput + `Ar-Ka Area` via `rep0["Instrument_z"]` (o pior dos dois z-scores, linha a linha); `ROLLING_VARS` (QC4) ganhou `Ar-Ka Area` como quarta variável opcional. Validado contra o arquivo de exemplo: distribuição de QF (default) passa de `{0:208, 2:45, 3:17}` para `{0:199, 1:1, 2:42, 3:28}`; sem regressão quando a coluna está ausente (fallback reproduz o baseline anterior). Detalhes completos em `TODO.md`.

#### 3. QC2/QC3 — Coherent/Incoherent Scatter

**MANTER** — mapeiam 1:1 para `qc_rh_la`/`qc_rh_la_inc` atuais. A nomenclatura conceitual do v4.2 é mais clara cientificamente — trazida só como *label* de exibição (chave i18n, item d), sem mudar a lógica.

✅ **INCORPORADO em 2026-07-28** — a variação por energia (`Rh-Ka-Coh`/`Rh-Ka-Inc` em 30 kV, ausente em 50 kV) foi implementada junto com a estrutura multi-energia (ver item 6 abaixo): `qc_rh_la`/`qc_rh_la_inc` recebem `energy` e resolvem a coluna física via `ENERGY_PARAMETERS`.

#### 4. QC4 — Rolling QC

✅ **INCORPORADO em 2026-07-28** — as duas diferenças identificadas nesta análise foram resolvidas:

1. **Persistência temporal**: implementada como **opt-in** (`use_rolling_persistence`, default `False`), sob alinhamento explícito do usuário (Andre Belem) — resolve a tensão com o item 1.5 do TODO sem alterar o default ("defesa em profundidade" continua sendo o comportamento padrão; a persistência é uma escolha explícita da sessão). Ver `qc_core._apply_rolling_persistence`/`qc_rolling` e `TODO.md`, seção "Bloqueados até decisão do time", para a implementação e validação completas.
2. Argônio no conjunto de variáveis do rolling — já incorporado junto com o item b (Argônio em QC1), ver seção 2 acima.

**DESCARTAR (mantido)** — v4.2 sempre combina as variáveis via máximo (equivalente a `combine_rolling_vars=True` fixo, sem opção). Contradiz a decisão de 2026-06-28 (item 4.1 do TODO) de que a variável incoerente sozinha é o default — **não portado**; `combine_rolling_vars` continua opt-in. Exceção graciosa: em 50 kV (sem variável incoerente), `compute_scores` cai automaticamente no modo combinado, já que não há variável espectral "default" a usar sozinha nessa energia.

#### 5. QC5 — Réplicas

**DESCARTAR (crítico)** — `replicates.py` do v4.2 casa réplicas por **igualdade exata de profundidade**. É exatamente o bug do achado C1, já corrigido (`REPLICATE_KEY_COLS = ["Spectrum", "CoreDepth"]`, `qc_core.py:246-269`): `CompositeDepth (mm)` fica nulo em Rep1/Rep2 no arquivo real. **Não portar essa parte do v4.2.**

✅ **INCORPORADO em 2026-07-28** — `rpd()`/`calculate_rpd` do v4.2 trata `mean == 0` retornando `NaN` explicitamente antes da divisão, em vez de propagar `inf`. Ver `TODO.md` item 1.1 para a validação (rodado com `-W error::RuntimeWarning`, sem regressão de QF).

**MODIFICAR (a discutir)** — v4.2 usa thresholds discretos de RPD (<10% OK, 10–20% ALERT, >20% CRITICAL) em vez da fórmula contínua atual (`100 - Mean_RPD*4`). Filosofias diferentes — só relevante se o modo de QF por contagem (item 7) for adotado.

#### 6. Estrutura multi-energia (10/30/50 kV) e detecção automática

✅ **INCORPORADO em 2026-07-28** — confirmado pelo usuário que arquivos reais sempre têm pelo menos 10 kV e 30 kV (50 kV opcional). `ENERGY_PARAMETERS`/`detect_energy` (`qc_core.py`) reproduzem `config.py`/`io_module.py` do apêndice; `read_workbook` lê todas as abas e detecta a energia de cada uma pelo nome. Todas as funções do pipeline ganharam parâmetro `energy=DEFAULT_ENERGY` ("10kV"), preservando o comportamento anterior byte a byte quando não especificado. **Descoberta relevante durante a validação:** `data/Dados Consolidados-ICCE3.xlsx` — usado em várias validações anteriores deste documento/TODO.md como exemplo de "testemunho de seção única" — na verdade é um workbook multi-energia real com 3 abas (`10kV`/`30kV`/`50kV`); a limitação do item 3.1 (`pd.read_excel` sem `sheet_name` só lê a primeira aba) fazia essas validações lerem, sem se perceber, apenas a aba `10kV`. Ver `TODO.md`, seção 9, item "Estrutura multi-energia" para detalhes completos e validação.

#### 7. Quality Flag — filosofia de agregação

A diferença mais profunda entre os dois documentos.

- **Atual**: QI contínuo ponderado (`QI_WEIGHTS`) + critérios pontuais de z-score/Mahalanobis sobrepostos (`compute_flags`, `qc_core.py:401-460`). Um módulo muito bom pode compensar outro ruim.
- **v4.2**: cada módulo vira um estado discreto (OK/ALERT/CRITICAL) e o QF final é contagem de estados (`evaluate_flag`): QF0 sem alerta, QF1 = 1 alerta, QF2 = 2-3 alertas ou 1 crítico, QF3 = 2+ críticos ou 4+ alertas. Não compensatório.

**INCORPORAR** — é literalmente o item 8.7, já registrado no `TODO.md` como funcionalidade planejada ("modo alternativo de QF por contagem de módulos reprovados vs. QI ponderado"), e o v4.2 entrega uma especificação pronta. Implementar como segundo modo **opt-in** (o QI ponderado continua default).

**DESCARTAR (crítico)** — `classify_z`/`classify_rolling` do v4.2 tratam `NaN` como `QC_OK` explicitamente. É exatamente o bug do achado C2, já corrigido (`QF_INDETERMINATE=9`, `is_indeterminate` calculado antes do loop, `qc_core.py:420`). Se o modo de contagem for incorporado, a lógica de NaN precisa produzir indeterminado, nunca OK — não portar essa parte literalmente.

#### 8. Produtos de saída (Excel/relatório)

✅ **INCORPORADO em 2026-07-28** (item c) — preenchimento de cor por célula no Excel (verde/amarelo/vermelho via `openpyxl.PatternFill`), restrito às colunas adicionadas pelo pipeline QC (nunca nas colunas originais do Avaatech). Ver `TODO.md`, seção 9, item c, para a divergência deliberada frente ao `reports.py` do apêndice (match numérico 0/1/2/3 restrito à coluna `QF`) e a validação completa. **Desde a implementação de multi-energia (2026-07-28)**, `to_excel_bytes` exporta um workbook com uma aba por energia processada, cada uma com sua própria coloração — não muda a lógica de coloração em si, só a passou a aplicar por aba.

**MANTER** — o relatório atual (PDF com página de intervalos problemáticos, causas traduzidas, ícone de flag pontual, nota de rodapé — `report_pdf.py`) é estruturalmente mais rico que o `QC_Summary.txt` simples do v4.2. Não vale substituir; no máximo, gerar um `.txt`/resumo simples como complemento rápido do PDF.

**MODIFICAR (a discutir)** — v4.2 preserva o `raw_data` completo (todas as réplicas Rep0/Rep1/Rep2) no Excel de saída, anotando QC só nas linhas Rep0. O `.xlsx` atual exporta só o subconjunto `rep0` filtrado. Pode valer a pena manter as réplicas brutas no export para rastreabilidade — confirmar se é desejado.

#### Tabela-síntese

| # | Item | Classificação |
|---|------|------|
| 1 | Layout de arquivos (config/main/io_module/qc/reports/replicates) | **DESCARTAR** |
| 2 | i18n, PCA diagnóstica, seletor de profundidade, PDF de intervalos | **MANTER** |
| 3 | Argônio (Ar-Ka Area) em QC1 | ✅ **INCORPORADO (2026-07-28)** |
| 4 | Nomenclatura "Coherent/Incoherent Scatter" como label | ✅ **INCORPORADO (2026-07-28)** — item d do `TODO.md`, seção 9 |
| 5 | Persistência temporal no QC4 (2 pontos consecutivos) | ✅ **INCORPORADO (2026-07-28)** — opt-in (`use_rolling_persistence`, default `False`); ver `TODO.md`, seção "Bloqueados até decisão do time" |
| 6 | Combinar sempre as variáveis no rolling (sem opt-in) | **DESCARTAR** |
| 7 | Casamento de réplica por igualdade exata de profundidade | **DESCARTAR (crítico — regride achado C1)** |
| 8 | `rpd()` com `mean==0` → NaN | ✅ **INCORPORADO (2026-07-28)** — item 1.1 do `TODO.md` |
| 9 | Thresholds discretos de RPD (10%/20%) | **MODIFICAR — só se item 12 for adotado** |
| 10 | Estrutura multi-energia (abas 10/30/50 kV) | ✅ **INCORPORADO (2026-07-28)** — `ENERGY_PARAMETERS`/`detect_energy`/`read_workbook`; ver `TODO.md`, seção 9 |
| 11 | NaN → sempre "OK" nos estados discretos | **DESCARTAR (crítico — regride achado C2)** |
| 12 | QF por contagem de módulos reprovados | ✅ **INCORPORADO (2026-07-28)** — item 8.7/seção 9(e) do `TODO.md` |
| 13 | Preenchimento de cor no Excel exportado | ✅ **INCORPORADO (2026-07-28)** — item c do `TODO.md`, seção 9 |
| 14 | QC_Summary.txt | **MANTER PDF atual; TXT como complemento opcional** |
| 15 | Exportar réplicas brutas junto no `.xlsx` | **MODIFICAR — confirmar com usuário** |

**Ordem de implementação sugerida e status de cada item:** ver seção "Histórico de achados e validações" abaixo (subseção "Protocolo v4.2 — itens priorizados de incorporação").

---

## Histórico de achados e validações

Registro completo de bugs corrigidos, decisões de implementação e validações contra dados reais. Movido do `TODO.md` em 2026-07-28 para manter aquele arquivo enxuto — `TODO.md` mantém só o que ainda está pendente. A numeração original (`1.1`, `2.2`, etc.) é preservada aqui só para rastreabilidade entre os dois arquivos.

### Achados críticos confirmados empiricamente (2026-06-28)

Estes dois itens não foram hipóteses — foram reproduzidos rodando `run_qc()` sobre o arquivo de exemplo do próprio repositório.

#### C1. QC5 (Réplicas) estava completamente inoperante com dados reais — RESOLVIDO (2026-06-28)

- **Arquivo/linha (na época do achado — ver `qc_core.py:246` para a localização atual após refatorações posteriores):** `qc_replicates`
- **Problema:** a função casava réplicas por igualdade exata de `DEPTH_COL` entre todas as linhas do `df` bruto. No arquivo de exemplo, **100% das linhas `Rep1`/`Rep2` têm `CompositeDepth (mm)` = NaN** (apenas `Rep0` tem profundidade preenchida). Resultado: `len(subset) < 2` para todas as profundidades, nenhum RPD era calculado, e a coluna `Mean_RPD` final era `NaN` para **todas as 270 linhas** (confirmado: `Mean_RPD.dtype == object`, `count() == 0`).
- **Efeito em cascata:** em `compute_scores` (linha 223-227), `Mean_RPD` NaN era mapeado para `Score_Replica = 100` (nota perfeita) via `np.where(rep0["Mean_RPD"].isna(), 100, ...)`. Ou seja, o módulo QC5 — 15% do peso do QI — estava silenciosamente sempre dando nota máxima, sem nenhum aviso ao usuário. `check_file` não detectava essa situação porque só validava presença de colunas, não a capacidade real de casar réplicas.
- **Investigação:** `CoreDepth` (idêntico a `X Position-mm`) nunca é nulo, inclusive nas réplicas — só `CompositeDepth (mm)` (profundidade já "composta"/ajustada do testemunho) é calculado apenas uma vez, na primeira passada. Agrupar por `(Spectrum, CoreDepth)` reproduz exatamente os trios Rep0+Rep1+Rep2 esperados (12 grupos de tamanho 3 no arquivo de exemplo, batendo com as 24 linhas de profundidade nula encontradas).
- **Correção aplicada:** nova constante `REPLICATE_KEY_COLS = ["Spectrum", "CoreDepth"]` em `qc_core.py`; `Spectrum`/`CoreDepth` adicionados a `REQUIRED_COLUMNS` (passam a ser obrigatórios e validados por `check_file` automaticamente); `qc_replicates` reescrita para agrupar via `df.groupby(REPLICATE_KEY_COLS)` em vez de iterar sobre `DEPTH_COL`, e o merge final usa a mesma chave composta.
- **Validação:** rodando contra `data/exemplo_dados_consolidados.xlsx`, `Mean_RPD` agora é `float64` com 12 valores reais (0.70%–5.03%) nas posições com réplica, e `Score_Replica` varia de 79.9 a 100 (em vez de ser sempre 100). As 258 posições sem réplica continuam corretamente como `NaN` → fallback de nota 100 (esse fallback em si é uma decisão de design separada — ver `TODO.md`, item 1.4 — não foi alterado nesta correção).

#### C2. QI/QF mascaravam dados faltantes como "OK" — RESOLVIDO (2026-06-28)

- **Arquivo/linha:** `qc_core.py` (`compute_scores`, `compute_flags`, `run_qc`)
- **Problema:** se `Throughput`, `Rh-La Area`, `Rh-La-Inc Area` (ou os deltas de rolling) tivessem `NaN` em qualquer linha, `robust_zscore` propagava `NaN`, `score_from_z(NaN)` = `NaN`, e o `QI` ponderado final também virava `NaN`. Em `compute_flags`, todas as comparações (`abs(row[z_col]) > 2`, `row["QI"] < 40`, `row["QI"] < 80`) retornavam `False` quando o operando era `NaN` (semântica padrão do Python/NumPy). Como nenhuma condição "disparava", a linha permanecia com `qf = 0` — uma medição com dado faltante crítico era classificada como "OK".
- **Correção aplicada:**
  - Nova constante `CRITICAL_INPUT_COLS = ["Throughput", "Rh-La Area", "Rh-La-Inc Area"]` (QC1-QC3, sempre obrigatórias) e `QF_INDETERMINATE = 9`, um código de flag **distinto** de 0-3 — nunca confundido com "OK" nem com "ruim" (essas são categorias diferentes: "avaliei e está mau" vs. "não consegui avaliar").
  - `compute_flags` agora calcula `is_indeterminate = rep0[CRITICAL_INPUT_COLS].isna().any(axis=1) | rep0["QI"].isna()` **antes** do loop de regras existente; linhas indeterminadas recebem `QF_INDETERMINATE` incondicionalmente, nunca caem no fallthrough para `qf=0`.
  - Adicionado um **checkbox de política** (`strict_missing_data`, exposto na sidebar de `qc_avaatech.py`, default `True`/restritivo) que controla *apenas* o cálculo do `QI` para essas linhas — nunca a detecção/flag em si, que é sempre ativa:
    - **Restritivo** (`strict_missing_data=True`, padrão): `QI = scores @ weights` — qualquer score ausente invalida o `QI` da linha (fica `NaN`).
    - **Flexível** (`strict_missing_data=False`): `QI` é recalculado só com os módulos disponíveis, redistribuindo os pesos nominais (`QI_WEIGHTS`) entre eles — útil para visualizar uma estimativa "best effort" em vez de um campo vazio, mas a linha continua com `QF=9` em ambos os modos.
- **UI:** `qc_avaatech.py` ganhou a 5ª cor/posição no gráfico QI/QF (`QF_COLORS`/`QF_PLOT_ORDER`, cinza, plotada numa posição visual separada para não distorcer a escala de gravidade 0-3) e uma 5ª métrica no resumo (`metric_qf_indeterminate`). `locales/pt.json` e `locales/en.json` ganharam as chaves `strict_missing_label`, `strict_missing_help`, `metric_qf_indeterminate`, e `plot_qf_labels` passou a ter 5 entradas.
- **Validação:** testado com `data/exemplo_dados_consolidados.xlsx` (sem regressão — distribuição de QF idêntica à anterior, pois o arquivo não tem NaN em QC1-QC3) e com NaN sintético injetado em `Throughput` de 5 linhas: em ambos os modos as 5 linhas recebem `QF=9` (nunca `QF=0`); no modo restritivo `QI=NaN`, no flexível `QI` fica entre ~85-96 (recalculado com os 5 módulos restantes). App Streamlit testado de ponta a ponta (`streamlit run`, HTTP 200, sem erro de import/runtime).

### Itens resolvidos por seção (numeração original do `TODO.md`)

**1.1** `qc_core.py` (`calculate_rpd`) — Resolvido em 2026-07-28 (incorporado do protocolo v4.2 do Igor). `mean == 0` agora retorna `NaN` explicitamente antes da divisão, em vez de propagar `inf` para `Mean_RPD`. Validado: `calculate_rpd([10, -10])` e `calculate_rpd([0, 0, 0])` retornam `NaN`; pipeline completo rodado contra `data/exemplo_dados_consolidados.xlsx` com `-W error::RuntimeWarning` sem levantar warning, distribuição de QF idêntica à anterior (`{0:208, 2:45, 3:17}`) — sem regressão.

**1.2 / 2.2** `qc_core.py` (`qc_pca`, `check_file`, `compute_scores`) — Resolvido em 2026-06-28. Decisão tomada: em vez de `check_file` bloquear com erro, o pipeline **degrada graciosamente** — consistente com o fallback que QC5 (réplicas) já usava. Novas constantes `MIN_PCA_ELEMENTS=2`/`MIN_PCA_ROWS=3`; `qc_pca` pula QC6 com PC1/PC2/Mahalanobis=NaN quando insuficiente; `compute_scores` aplica `Score_PCA=100` (neutro, mesmo padrão de `Score_Replica`) quando `Mahalanobis` está todo nulo; `check_file` emite **warnings** bilíngues dedicados (`pca_unavailable`, `pca_too_few_rows`); `qc_avaatech.py` mostra `st.info` na aba PCA em vez de um gráfico vazio sem explicação. Validado com arquivo real (sem regressão) + 3 cenários sintéticos (0 elementos, 1 elemento, 2 linhas Rep0) — nenhum gera exceção, QI permanece computável em todos.

**1.3** `qc_core.py` (`qc_pca`) — Resolvido em 2026-06-28: `np.linalg.inv(cov)` trocado por `np.linalg.pinv(cov)`, mais robusto a matriz quase-singular.

**1.5** `qc_core.py` (`compute_flags`) — Resolvido em 2026-06-28. Critérios de flag são avaliados com `max(qf, ...)`, então um único z-score pontualmente alto (entre 2 e 3) já força `QF=2` mesmo que o `QI` agregado esteja alto (≥80) — isso é intencional (defesa em profundidade), mas agora é detectado e explicado: `is_pointwise_flag(rep0)` identifica essas linhas, e `add_pointwise_flag_notes` expõe a explicação traduzida (coluna `Pointwise_Flag_Note`, visível na tabela da UI e no `.xlsx`), usando as causas já registradas em `QF_Causes`. `report_pdf.py` também marca esses casos no PDF (ícone "⚠" + nota de rodapé).

**3.1** `qc_avaatech.py` (leitura do upload) — Resolvido como efeito colateral da implementação de multi-energia (2026-07-28, ver seção 9 abaixo): `pd.read_excel(uploaded)` sem `sheet_name` (que lia só a primeira aba silenciosamente) foi substituído por `read_workbook(uploaded)`, que lê todas as abas do workbook e detecta a energia de cada uma. Não há mais leitura parcial e silenciosa de um workbook multi-aba.

**3.6** `qc_core.py` (`REQUIRED_COLUMNS`, `check_file`, `run_qc`) — Resolvido em 2026-07-28, achado ao validar um novo arquivo real (`Dados Consolidados-ICCE3.xlsx`, testemunho de seção única na época): o arquivo não exporta `CompositeDepth (mm)` (`DEPTH_COL`), só `CoreDepth` — `DEPTH_COL` era obrigatório em `REQUIRED_COLUMNS`, então `check_file` bloqueava a execução inteira do pipeline com erro, mesmo o arquivo sendo estruturalmente válido. **Correção:** `DEPTH_COL` removido de `REQUIRED_COLUMNS` (só `CORE_DEPTH_COL`, via `REPLICATE_KEY_COLS`, continua obrigatório). `run_qc` sintetiza `rep0[DEPTH_COL] = rep0[CORE_DEPTH_COL]` quando a coluna original está ausente, antes de qualquer sort/cálculo. `check_file` ganhou o aviso `depth_col_fallback`, e o check de `dup_depths` passou a usar a coluna efetivamente resolvida. **Limitação assumida, avisada no texto do warning:** só é correto para testemunho de **seção única** — `CoreDepth` reinicia a cada seção, então um arquivo multi-seção sem `CompositeDepth` produziria profundidades/intervalos incorretos nas transições. **Validado:** `Dados Consolidados-ICCE3.xlsx` (65 linhas Rep0, 1 seção) roda sem erro nos dois modos de QF (`{0:49,2:7,3:9}` ponderado / `{0:54,1:4,2:7}` contagem); `data/exemplo_dados_consolidados.xlsx` revalidado sem regressão. Nova chave `depth_col_fallback` em `locales/pt.json`/`en.json`. **Nota (2026-07-28):** essa validação usava `pd.read_excel(f)` sem `sheet_name` (item 3.1 acima) — só depois de implementar suporte multi-energia se descobriu que `Dados Consolidados-ICCE3.xlsx` na verdade tem **3 abas** (`10kV`/`30kV`/`50kV`); os números acima são especificamente da aba `10kV`, não do arquivo completo.

**4.1** `qc_core.py` (`qc_rolling`/`compute_scores`/`compute_flags`) — Resolvido em 2026-06-28 (revisado no mesmo dia). Nova constante `ROLLING_VARS`; `compute_scores(rep0, combine_rolling_vars=False)` calcula `rep0["Rolling_z"] = max(|Throughput_delta_z|, |Rh-La Area_delta_z|, |Rh-La-Inc Area_delta_z|)` quando `combine_rolling_vars=True` — o máximo, não a média, porque um problema físico real tende a aparecer com força em pelo menos uma das três. `compute_flags` passou a usar `rep0["Rolling_z"]` em vez do literal `"Rh-La-Inc Area_delta_z"`. **Decisão final de default:** `combine_rolling_vars=False` é o default — QC4 considera só `Rh-La-Inc Area` por padrão (dado espectral real); combinar as três é opt-in via checkbox. README atualizado.

*(discussão de design)* Antes de decidir a implementação, foi avaliada e descartada a ideia de 3 checkboxes independentes (um por variável). Motivo: (1) combinações sem resposta clara; (2) é uma decisão **metodológica** sobre a fórmula do QC4, deveria ser a mesma para todos os usuários/sessões; (3) risco de um usuário zerar silenciosamente o único sinal que sustentava o score.

**4.6** `qc_avaatech.py` (tabela exibida) — Resolvido em 2026-06-28. `st.dataframe(rep0[display_cols], ...)` exibe os nomes de coluna originais do Avaatech (não traduzidos) — inconsistente à primeira vista, mas intencional; documentado explicitamente em `CLAUDE.md`.

**5.2** `qc_core.py` (`qc_replicates`) — Resolvido em 2026-06-28 como parte da correção do achado C1: a função usa `df.groupby(REPLICATE_KEY_COLS)` em vez de iterar e refiltrar o `df` a cada profundidade.

**8.5** Seletor de coluna de profundidade exibida (`CompositeDepth` vs. `CoreDepth`) — Implementado em 2026-06-28: `qc_avaatech.py` ganhou um seletor na sidebar (`DEPTH_DISPLAY_COL`) para escolher entre `CompositeDepth (mm)` (padrão) e `CoreDepth` (`qc_core.CORE_DEPTH_COL`) como coluna de profundidade no eixo X dos gráficos, na tabela exibida e no relatório PDF. **Puramente de exibição — não afeta nenhum cálculo do pipeline**; `REPLICATE_KEY_COLS` permanece inalterado. Todas as funções `plot_*` passaram a receber `depth_col=DEPTH_COL`; `report_pdf.detect_intervals`/`build_problem_intervals_page` ganharam o parâmetro, mas a ordenação/decisão de gap usa **sempre** `qc_core.DEPTH_COL` (contínua/monotônica), nunca `depth_col` — usar `CoreDepth` para essa decisão misturaria transições de seção. **Limitação conhecida:** num testemunho multi-seção, um intervalo que cruze uma transição pode reportar `depth_end < depth_start` quando `depth_col=CoreDepth` (2 dos 37 intervalos no arquivo de exemplo) — puramente cosmético, contagem/causas idênticas nos dois modos. Novas chaves: `depth_display_label/composite/core/help`. Validado de ponta a ponta (HTTP 200).

**8.6** PCA (QC6) sempre diagnóstica, mas opcional no critério de QF — Implementado em 2026-06-28. Novo parâmetro `include_pca_in_qf` (default `False`) em `compute_scores`, `compute_flags` e `run_qc`. Quando `False`: `Score_PCA` continua sempre calculado, mas é excluído da soma ponderada do `QI` (pesos restantes renormalizados para somar 1.0). A checagem **direta** de `Mahalanobis > p95/p99` em `compute_flags` (que dispara `QF=2/3` independente do QI) também só roda quando `include_pca_in_qf=True` — senão a PCA continuaria influenciando o QF por um caminho paralelo mesmo com peso zero no QI. Checkbox `include_pca_qf_label` na sidebar. **Validado** contra `data/exemplo_dados_consolidados.xlsx`: `include_pca_in_qf=True` reproduz a distribuição de QF anterior à mudança (`{0:201, 2:49, 3:20}`); default `False` dá `{0:208, 2:45, 3:17}`. README atualizado ("About QC6").

**8.7** Seletor de modo de QF: QI ponderado vs. contagem de módulos reprovados — Implementado em 2026-07-28 como item (e) do protocolo v4.2 (ver abaixo). Novo parâmetro `use_count_mode` (opt-in, default `False`) em `compute_flags`/`run_qc`, checkbox correspondente em `qc_avaatech.py`. Modo QI ponderado continua sendo o default.

**8.8** Empacotamento como executável standalone (PyInstaller) — Implementado em 2026-06-29: diretório `installer/` empacota o app como executável standalone (Windows `.exe` / binário Linux), sem exigir Python/`.venv` na máquina de destino. `installer/launcher.py` invoca `streamlit.web.cli` programaticamente (Streamlit não pode ser entry point direto do PyInstaller), desliga o file watcher (`--server.fileWatcherType=none` — evita `RuntimeError: dictionary changed size during iteration`, race condition conhecida). `installer/lamplus_qc.spec` usa `collect_all()` para `streamlit`/`scipy`/`sklearn`/`matplotlib` e copia os módulos/`locales`/`assets` do projeto como dados brutos. **Bug real encontrado e corrigido:** Python via conda/miniforge no Windows guarda DLLs nativas (`ffi-8.dll`, tcl/tk, sqlite3, bz2, expat) em `Library/bin/` em vez de `DLLs/` — corrigido localizando via `sys.base_prefix` no `.spec`. **Validado de ponta a ponta no Windows em 2026-06-29:** executável onefile gerado (~150MB), executado, servidor Streamlit responde HTTP 200. **Não testado no Ubuntu** (sem ambiente disponível na sessão). `.exe` nunca commitado — distribuição via GitHub Releases.

### Protocolo v4.2 (Igor Oliveira) — itens priorizados de incorporação

Análise comparativa completa entre o protocolo v4.2 e o pipeline atual (texto do protocolo, classificações INCORPORAR/MODIFICAR/MANTER/DESCARTAR e tabela-síntese) está na seção "Protocolo v4.2 — Análise e Roadmap de Incorporação" mais acima neste documento. Abaixo, o registro de implementação de cada item priorizado (todos concluídos em 2026-07-28, exceto o item ainda bloqueado listado no `TODO.md`):

**a. Correção `calculate_rpd`** — ver item 1.1 acima.

**b. Argônio (`Ar-Ka Area`) em QC1 e QC4** — Implementado. Nova constante `ARGON_COL = "Ar-Ka Area"`. `qc_throughput` (QC1) combina Throughput + Argônio via `rep0["Instrument_z"]` = o z-score de maior magnitude absoluta entre os dois, linha a linha ("pior dos dois"); `Throughput_z`/`Argon_z` continuam disponíveis individualmente como diagnóstico. `Score_Throughput` e o critério pontual de QF passaram a usar `Instrument_z`; nova causa `CAUSE_ARGON` atribuída dinamicamente conforme qual dos dois z-scores foi o pior. `ROLLING_VARS` ganhou `Ar-Ka Area` como quarta variável (só usada quando `combine_rolling_vars=True`); `qc_rolling` ignora graciosamente qualquer variável ausente do arquivo. Nova chave `cause_argon`. **Validado** contra `data/exemplo_dados_consolidados.xlsx`: distribuição de QF (default) passa de `{0:208, 2:45, 3:17}` para `{0:199, 1:1, 2:42, 3:28}` (20 linhas onde o Argônio é o pior dos dois, 11 cruzando o limiar de flag); com `combine_rolling_vars=True`, `{0:174, 2:79, 3:17}` → `{0:155, 2:87, 3:28}`. Testado removendo `Ar-Ka Area`: `Argon_z` fica `NaN`, `Instrument_z` cai de volta para `Throughput_z` puro, distribuição reproduz exatamente o baseline anterior — sem regressão para arquivos sem Argônio.

**c. Coloração verde/amarelo/vermelho no `.xlsx` exportado** — Implementado. `to_excel_bytes` ganhou parâmetro `original_columns`; colunas adicionadas por `run_qc`/`compute_scores`/`compute_flags`/`add_pointwise_flag_notes` recebem `openpyxl.PatternFill` célula a célula via `_qc_cell_fill` — verde (`C6EFCE`) para QF=0/"OK"/"NO", amarelo (`FFF2CC`) para QF=1/"WARNING", vermelho (`F4CCCC`) para QF∈{2,3}/"CRITICAL"/"YES". Colunas originais do Avaatech nunca são tocadas. **Divergência deliberada do `reports.py` do apêndice v4.2:** aqui `QF` é int (não string `"QF0"`...) e várias colunas numéricas contínuas (`Score_Replica`, `Score_PCA`, RPD, z-scores) legitimamente assumem 0-3 sem relação com severidade — por isso o match numérico 0-3 foi restrito à coluna `QF`. `QF_INDETERMINATE` (9) fica sem preenchimento (intencional). Validado: 199 células QF=0→verde, 1 QF=1→amarelo, 42 QF=2 + 28 QF=3→vermelho; colunas originais confirmadas sem preenchimento.

**d. Labels "Coherent Scatter"/"Incoherent Scatter" como chaves i18n** — Implementado. `plot_rh1_title`/`plot_rh2_title` passaram a incluir o nome conceitual do v4.2 junto ao nome técnico: PT `"QC2 — Espalhamento Coerente (Rh-Lα)"`/`"QC3 — Espalhamento Incoerente (Rh-Lα-Inc)"`. Lógica de `qc_rh_la`/`qc_rh_la_inc` intocada. `plot_throughput_title` corrigido pelo mesmo motivo para `"QC1 — Estabilidade do Instrumento (Throughput)"`. QC4/QC5 já usavam nomenclatura conceitual, sem mudança. Validado: paridade de chaves PT/EN mantida.

**e. Modo de QF por contagem de módulos reprovados (opt-in)** — Implementado. Novo parâmetro `use_count_mode` (default `False`) em `compute_flags`/`run_qc`; 4º checkbox na sidebar. Cada módulo é classificado em OK/ALERT/CRITICAL via limiares nomeados específicos deste modo (`COUNT_MODE_Z_WARNING=2.5`/`COUNT_MODE_Z_CRITICAL=3.5`, `COUNT_MODE_ROLLING_Z_ALERT=4.0`, `COUNT_MODE_RPD_WARNING=10.0`/`COUNT_MODE_RPD_CRITICAL=20.0`), distintos dos limiares do modo QI ponderado. `_evaluate_flag_count_mode`: QF0 sem alerta, QF1=1 ALERT, QF2=2-3 ALERTs ou 1 CRITICAL, QF3=2+ CRITICALs ou 4+ ALERTs — não compensatório. Nova causa `CAUSE_REPLICA`. **NaN nunca vira OK:** `is_indeterminate` roda antes do branch de contagem, incondicionalmente nos dois modos — a lógica do apêndice v4.2 que trata NaN como OK **não foi portada**. **Validado**: modo QI ponderado mantém `{0:199, 1:1, 2:42, 3:28}` (sem regressão); modo de contagem dá `{0:229, 1:20, 2:21}`; teste de NaN sintético confirma `QF=9` nos dois modos, nunca `QF=0`.

**Persistência temporal no QC4** — Implementado em 2026-07-28, sob alinhamento explícito do usuário (Andre Belem), como **opt-in** (`use_rolling_persistence`, default `False` — preserva "defesa em profundidade" como comportamento padrão). Novas constantes `ROLLING_PERSISTENCE_Z_THRESHOLD=2.0`, `ROLLING_PERSISTENCE_MIN_POINTS=2`, `ROLLING_PERSISTENCE_WINDOW=3`. `_apply_rolling_persistence`: um ponto com `|delta_z| > threshold` só mantém seu z-score se houver ≥2 pontos acima do limiar numa janela de 3 medidas centrada nele; anomalias isoladas são zeradas antes do resto do pipeline. **Bug pego e corrigido durante a validação:** a primeira implementação zerava todo ponto não-persistente, incluindo pontos nunca anômalos — corrigido para só zerar `anomaly & ~persistent`. Checkbox `rolling_persistence_label` na sidebar. **Validado:** `use_rolling_persistence=False` reproduz exatamente as distribuições anteriores nos dois arquivos e nos dois modos — sem regressão. `use_rolling_persistence=True`: `exemplo_dados_consolidados.xlsx` vai a `{0:202,1:1,2:39,3:28}` ponderado / `{0:229,1:20,2:21}` contagem (idêntico); `Dados Consolidados-ICCE3.xlsx` vai a `{0:52,2:4,3:9}` ponderado / `{0:54,1:4,2:7}` contagem (idêntico).

**Estrutura multi-energia (10/30/50 kV)** — Implementado em 2026-07-28, sob confirmação explícita do usuário: "arquivos reais sempre têm pelo menos 10 kV e 30 kV; 50 kV é opcional". **Descoberta ao validar:** `data/Dados Consolidados-ICCE3.xlsx` já é um workbook multi-energia real (3 abas) — antes desta mudança, `pd.read_excel()` sem `sheet_name` lia só a primeira aba silenciosamente (item 3.1 acima), então validações anteriores contra esse arquivo eram, sem se perceber, só da aba `10kV`.

- **`qc_core.py`:** `ENERGY_PARAMETERS` (espelha `config.py` do apêndice) — dict `{"10kV"/"30kV"/"50kV": {"throughput", "argon", "coherent", "incoherent"}}`, confirmado contra as colunas reais das 3 abas do ICCE3. `detect_energy(sheet_name)` reproduz `io_module.py` do apêndice (substring "10"/"30"/"50" no nome da aba, case-insensitive). `DEFAULT_ENERGY="10kV"` — todas as funções do pipeline ganharam `energy=DEFAULT_ENERGY` opcional, reproduzindo o comportamento anterior byte a byte quando não especificado. `REQUIRED_COLUMNS`/`CRITICAL_INPUT_COLS`/`ROLLING_VARS` agora derivadas de `ENERGY_PARAMETERS` via `_required_columns_for_energy`/`_critical_cols_for_energy`/`_rolling_vars_for_energy`.
- **Módulos estruturalmente inaplicáveis** (ex. Rh-Lα/Rh-Lα-Inc em 50 kV): tratados como caso *estrutural* (dataset inteiro não mede aquele parâmetro), não *dado faltante pontual* (achado C2). `compute_scores` força `Score_RhLa`/`Score_RhLaInc=100` e exclui o peso correspondente do `QI` (renormalizado); `compute_flags` usa `_critical_cols_for_energy`. QC4 cai automaticamente no modo combinado quando a variável incoerente não existe (50 kV).
- **`qc_avaatech.py`:** `read_workbook(uploaded)` lê todas as abas e detecta a energia de cada uma; abas com energia não reconhecida são ignoradas (exceto workbook de aba única, que assume `DEFAULT_ENERGY`). `check_file`/`run_qc` rodam por aba, independentemente — uma aba com erro não bloqueia as demais. Seletor de aba/energia só aparece com mais de uma aba processada. `plot_rh`/`plot_rolling` ganharam parâmetro `energy`. `to_excel_bytes` exporta um workbook com uma aba por energia processada.
- **Validado** com `-W error::RuntimeWarning` (sem warnings), 32 combinações de parâmetros por aba:
  - `exemplo_dados_consolidados.xlsx` (aba única `10kv`): `{0:199,1:1,2:42,3:28}` ponderado / `{0:229,1:20,2:21}` contagem — idêntico ao baseline, sem regressão.
  - `Dados Consolidados-ICCE3.xlsx`, aba `10kV`: `{0:49,2:7,3:9}` ponderado / `{0:54,1:4,2:7}` contagem — idêntico ao baseline anterior.
  - `Dados Consolidados-ICCE3.xlsx`, aba `30kV`: `{0:38,2:17,3:10}` ponderado, módulo Rh-Kα-Coh/Inc ativo.
  - `Dados Consolidados-ICCE3.xlsx`, aba `50kV`: `{0:46,2:10,3:9}` ponderado, `Score_RhLa`/`Score_RhLaInc` sempre `100` (módulo corretamente neutro/excluído), `QI` ainda computável (média 84.9).
  - Export `.xlsx` do ICCE3 gerado com 3 abas nomeadas, cada uma preservando todas as colunas originais + colunas de QC. App Streamlit testado de ponta a ponta (HTTP 200).
- Novas chaves: `workbook_sheets_info`, `workbook_skipped_warning`, `energy_sheet_selector_label`, `rh_not_applicable_info`; `plot_rolling_title` virou template (`{var}`).

### Validação em lote — arquivos reais adicionais (2026-07-28)

Depois da implementação de multi-energia, o usuário disponibilizou mais 5 arquivos reais em `data/` além de `exemplo_dados_consolidados.xlsx` e `Dados Consolidados-ICCE3.xlsx`: `Dados Consolidados-Itatiaia.xlsx` (2 abas: 10kV/30kV), `Dados Consolidados-OP42GC4.xlsx` (3 abas: 10kV/30kV/50kV), `Dados Consolidados-dgl1905.xlsx` (3 abas: 10kV/30kV/50kV, ~10.500 linhas Rep0 por aba — o maior arquivo do conjunto), `Dados Consolidados-trigoskoe.xlsx` (2 abas: 10kV/30kV) e `Dados ConsolidadosICCE10.xlsx` (3 abas: 10kV/30kV/50kV).

Rodado o pipeline completo (`run_qc` com os defaults atuais) contra os 6 arquivos, uma aba por vez via `read_workbook`/`check_file`/`run_qc`, gerando um PDF de relatório por arquivo em `data/reports/<nome>.pdf`. **Nenhum arquivo falhou** — todas as 16 abas processaram sem erro de `check_file` nem exceção em `run_qc`.

Distribuições de QF (modo ponderado, defaults) por arquivo/aba:

| Arquivo | Aba (energia) | n(Rep0) | QF |
|---|---|---|---|
| Dados Consolidados-ICCE3.xlsx | 10kV / 30kV / 50kV | 65 / 65 / 65 | `{0:49,2:7,3:9}` / `{0:38,2:17,3:10}` / `{0:46,2:10,3:9}` |
| Dados Consolidados-Itatiaia.xlsx | 10kV / 30kV | 77 / 77 | `{0:64,2:12,3:1}` / `{0:58,2:13,3:6}` |
| Dados Consolidados-OP42GC4.xlsx | 10kV / 30kV / 50kV | 557 / 557 / 557 | `{0:427,2:63,3:67}` / `{0:413,2:81,3:63}` / `{0:424,2:77,3:56}` |
| Dados Consolidados-dgl1905.xlsx | 10kV / 30kV / 50kV | 10518 / 10518 / 10518 | `{0:7608,1:20,2:1712,3:1178}` / `{0:8743,1:55,2:1118,3:602}` / `{0:8805,1:502,2:744,3:467}` |
| Dados Consolidados-trigoskoe.xlsx | 10kV / 30kV | 96 / 96 | `{0:73,1:1,2:13,3:9}` / `{0:74,1:2,2:16,3:4}` |
| Dados ConsolidadosICCE10.xlsx | 10kV / 30kV / 50kV | 88 / 88 / 88 | `{0:59,2:14,3:15}` / `{0:72,2:8,3:8}` / `{0:67,2:14,3:7}` |

Avisos de `check_file` em todas as abas seguiram os padrões já conhecidos e sem erro: fallback `CompositeDepth (mm)` → `CoreDepth`, elementos de PCA/réplica ausentes por energia (esperado), e linhas com Throughput zero/nulo (ICCE3, OP42GC4).

**⚠️ Alerta encontrado — `Dados Consolidados-dgl1905.xlsx`:** as 3 abas reportam **9311 profundidades duplicadas em Rep0** (de 10518 linhas — quase 89%), muito acima do observado em qualquer outro arquivo (0 duplicatas nos demais). O aviso `dup_depths` já existia em `check_file` e não bloqueia a execução, mas o volume aqui é atípico. **Hipótese mais provável:** este arquivo usa o fallback `CompositeDepth (mm)` ausente → `CoreDepth` (mesmo aviso `depth_col_fallback` apareceu nas 3 abas) — `CoreDepth` reinicia a cada seção, então se `dgl1905` tiver múltiplas seções, valores se repetem entre seções e aparecem como "duplicados". **Não investigado a fundo nesta sessão** — item de acompanhamento registrado em `TODO.md` ("Próximos passos identificados").

PDFs gerados (um por arquivo, não versionados no git): `data/reports/Dados Consolidados-ICCE3.pdf`, `Dados Consolidados-Itatiaia.pdf`, `Dados Consolidados-OP42GC4.pdf`, `Dados Consolidados-dgl1905.pdf`, `Dados Consolidados-trigoskoe.pdf`, `Dados ConsolidadosICCE10.pdf`. Cada um contém, por aba: os 6 gráficos de diagnóstico + a página de intervalos problemáticos. Gerados por um script de lote ad-hoc (não versionado no repositório).
