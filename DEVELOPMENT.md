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
