# TODO — LAM+ Core QC

Este arquivo contém apenas pendências reais, decisões em aberto, itens bloqueados e próximos passos. O histórico completo de achados, correções e validações está em `DEVELOPMENT.md`.

---

## 1. Decisões metodológicas pendentes

### 1.1 Política para ausência de réplicas

Hoje, quando `Mean_RPD` é `NaN`, o módulo de réplicas recebe score neutro/perfeito.

Decidir se a ausência de réplica deve:

- continuar neutra;
- receber score intermediário;
- gerar warning específico;
- produzir QF indeterminado em determinadas condições.

Essa decisão deve ser metodológica e validada com o time antes de alterar o comportamento atual.

### 1.2 Exportação das réplicas brutas

O Excel exportado contém atualmente apenas `Rep0`.

Decidir se o arquivo final deve preservar também:

- Rep1;
- Rep2;
- todas as colunas originais do workbook.

Caso seja adotado, definir como associar as colunas de QC apenas às linhas `Rep0` sem alterar a estrutura original das demais réplicas.

### 1.3 Parâmetros discretos de RPD

O modo por contagem utiliza thresholds de RPD de 10% e 20%.

Avaliar se esses valores devem:

- permanecer fixos;
- ser configuráveis;
- variar por elemento;
- ser calibrados com base em materiais de referência ou replicatas históricas do LAM+.

---

## 2. Robustez do pipeline

### 2.1 Guarda para ausência de Rep0

Adicionar validação explícita no início de `run_qc()`.

Quando não houver nenhuma linha `Rep0`, o pipeline deve interromper com uma mensagem clara, em vez de falhar posteriormente em módulos estatísticos.

### 2.2 Validação de tipos numéricos

Adicionar checagem de `dtype` para:

- profundidade;
- Throughput;
- parâmetros de espalhamento;
- Argônio;
- elementos usados em PCA;
- elementos usados em réplicas.

Quando possível, informar quais colunas foram lidas como texto ou contêm valores não conversíveis.

### 2.3 Normalização do identificador de réplica

Avaliar normalização de `Replicate Nr Count` com:

- remoção de espaços;
- comparação case-insensitive;
- warning quando o valor original precisar ser corrigido.

Exemplos problemáticos:

```text
Rep0 
REP0
rep0
```

### 2.4 Plausibilidade física

Adicionar warnings opcionais para valores fisicamente improváveis, como:

- Throughput negativo;
- áreas de contagem negativas;
- valores não finitos;
- proporção anormalmente alta de zeros.

Os limites não devem rejeitar dados automaticamente.

### 2.5 Escopo do warning de Throughput zero

Revisar se a contagem deve considerar:

- todo o dataframe bruto;
- apenas `Rep0`.

A mensagem deve informar explicitamente o escopo usado.

### 2.6 Arquivos muito grandes

Adicionar warning antes do processamento quando o número de linhas exceder um limite definido.

O objetivo é evitar travamentos inesperados da interface.

---

## 3. Profundidade e testemunhos multi-seção

### 3.1 Investigar `Dados Consolidados-dgl1905.xlsx`

Confirmar:

- número de seções;
- colunas `CoreID` e `SectionID`;
- existência de alguma informação suficiente para reconstruir `CompositeDepth (mm)`;
- origem das 9.311 profundidades duplicadas em Rep0.

Não considerar os intervalos problemáticos desse arquivo como definitivos antes dessa investigação.

### 3.2 Tratamento formal de arquivos sem `CompositeDepth (mm)`

Implementar uma política explícita para arquivos multi-seção sem profundidade composta.

Alternativas a avaliar:

- bloquear o processamento;
- exigir seleção manual de coluna;
- reconstruir profundidade a partir de metadados de seção;
- processar cada seção separadamente;
- permitir processamento com warning severo e desativar intervalos contínuos.

### 3.3 Intervalos exibidos em `CoreDepth`

Corrigir o caso em que um intervalo que cruza transição de seção pode apresentar:

```text
depth_end < depth_start
```

A contagem e as causas estão corretas, mas a apresentação é confusa.

---

## 4. Rolling QC

### 4.1 Janela em unidades físicas

`ROLLING_WINDOW = 5` representa cinco pontos, independentemente do espaçamento amostral.

Avaliar:

- configuração manual na UI;
- derivação a partir do espaçamento médio;
- janela em milímetros;
- comportamento para espaçamento irregular.

### 4.2 Calibração da persistência temporal

Validar com mais testemunhos os parâmetros:

- limiar de z;
- janela de três pontos;
- mínimo de dois pontos.

Verificar especialmente se o comportamento é consistente em resoluções de varredura diferentes.

---

## 5. PCA e análise multivariada

### 5.1 Exibir elementos usados

Mostrar na aba PCA quais elementos foram efetivamente utilizados.

O dado já é retornado por `run_qc()` como `pca_elements`.

### 5.2 Aviso para datasets pequenos

Adicionar aviso quando o número de linhas for insuficiente para estimativas robustas dos percentis de Mahalanobis.

Valor inicial a avaliar:

```text
n < 30
```

### 5.3 Vetores de loadings

Adicionar biplot com vetores dos elementos.

Antes de implementar, decidir:

- escala das setas;
- seleção de todos os elementos ou apenas os mais influentes;
- forma de evitar poluição visual;
- apresentação da variância explicada.

### 5.4 Clusters

Avaliar clustering no espaço multivariado.

Decisões necessárias:

- K-means ou método hierárquico;
- número fixo ou automático de clusters;
- uso apenas visual ou influência no QC;
- relação com a filosofia de não confundir composição incomum com falha de aquisição.

Por padrão, clusters não devem alterar QF sem uma decisão metodológica explícita.

### 5.5 Vetorizar Mahalanobis

Substituir o cálculo linha a linha por álgebra matricial, por exemplo com `np.einsum`.

---

## 6. Relatório PDF

### 6.1 Relatório completo por testemunho

Concluir `report_pdf.py` com:

- capa;
- logo;
- nome do testemunho;
- profundidade;
- número de medições;
- data e hora;
- opções de QC usadas;
- gráficos de diagnóstico;
- intervalos problemáticos;
- causas;
- observações.

### 6.2 Agrupamento por testemunho

Implementar função para extrair o nome do testemunho a partir de `Spectrum`.

Exemplo:

```text
lontra-T01
lontra-T02
```

devem ser agrupados como testemunho:

```text
lontra
```

Usar regex com fallback seguro quando o padrão não for reconhecido.

### 6.3 Integração com a interface

Adicionar:

- seletor de testemunho;
- opção “Todos”;
- geração de um PDF por testemunho;
- `.zip` quando houver múltiplos PDFs;
- botão de download ao lado do Excel;
- geração apenas quando solicitada.

### 6.4 Campo Operador

Adicionar campo de texto na UI e incluir o valor na capa do PDF.

### 6.5 Campo Comentários/Observações

Adicionar `st.text_area` e incluir o conteúdo no relatório.

Criar as chaves correspondentes em PT e EN.

### 6.6 Transformar o script de lote em função reutilizável

A geração usada na validação em lote foi feita por script ad-hoc.

Criar uma função oficial para gerar relatório completo por arquivo, sem depender de importações informais do frontend.

---

## 7. Performance

### 7.1 Vetorizar `compute_flags`

Substituir `iterrows()` por máscaras booleanas e `np.select`/`np.where`.

Prioridade alta para arquivos com milhares de linhas, como dgl1905.

### 7.2 Cache do Streamlit

Adicionar `@st.cache_data` para:

- leitura do workbook;
- validação;
- execução do QC.

A chave deve considerar:

- conteúdo do arquivo;
- energia;
- opções metodológicas selecionadas.

### 7.3 Cache de gráficos

Avaliar cache por:

- dados;
- idioma;
- coluna de profundidade;
- opções de QC.

### 7.4 Teste de desempenho

Criar benchmark mínimo com o arquivo dgl1905 e registrar:

- tempo de leitura;
- tempo por aba;
- tempo de PCA;
- tempo de flags;
- tempo de exportação;
- uso aproximado de memória.

---

## 8. Qualidade e manutenção do código

### 8.1 Type hints

Adicionar type hints às funções públicas de `qc_core.py`, `report_pdf.py` e helpers principais.

### 8.2 Constantes para limiares

Extrair os números mágicos restantes, incluindo:

- z = 2;
- z = 3;
- QI = 40;
- percentis 95 e 99.

### 8.3 Fonte única para labels de QF

Centralizar o mapeamento:

```text
QF0
QF1
QF2
QF3
QF9
```

e suas chaves de tradução.

### 8.4 Suíte automatizada

Criar diretório `tests/` com cobertura mínima para:

- C1 — casamento de réplicas;
- C2 — NaN nunca vira OK;
- RPD com média zero;
- dataset sem Rep0;
- PCA indisponível;
- energia 50 kV;
- workbook multi-aba;
- fallback de profundidade;
- modo ponderado;
- modo por contagem;
- persistência do rolling;
- paridade PT/EN;
- exportação Excel multi-aba.

### 8.5 Fixação de dependências

Definir versões mínimas e máximas testadas.

Avaliar:

- `requirements.txt` com ranges;
- `requirements-lock.txt`;
- ou migração para `pyproject.toml`.

### 8.6 Encapsular a aplicação Streamlit

Considerar mover o corpo imperativo de `qc_avaatech.py` para uma função `main()`.

### 8.7 Versão única do aplicativo

Remover versão hardcoded dos dois arquivos JSON.

Criar uma fonte única, por exemplo:

```python
__version__ = "..."
```

### 8.8 Idiomas suportados

Gerar as opções de idioma a partir de `SUPPORTED_LANGS`, eliminando duplicação entre `i18n.py` e `qc_avaatech.py`.

### 8.9 Validação de paridade i18n

Criar teste que compare as chaves de:

- `TEXTS`;
- `CHECK_MESSAGES`;
- estruturas aninhadas.

### 8.10 Tratamento de exceções

Substituir mensagens brutas de pandas/sklearn por:

- mensagem amigável e traduzida;
- detalhes técnicos em área expansível.

---

## 9. Compatibilidade e distribuição

### 9.1 Testar o executável no Ubuntu

Gerar o binário e validar:

- inicialização;
- carregamento de locales;
- leitura de arquivos;
- geração de Excel;
- geração de PDF;
- atalhos;
- dependências nativas.

### 9.2 Suporte a outros formatos

Avaliar suporte a:

- `.xls`;
- `.csv`.

Caso não seja implementado, explicitar a limitação para `.xlsx` na interface.

### 9.3 Nome do arquivo exportado

Decidir se o nome deve permanecer único em inglês ou ser localizado por idioma.

---

## 10. Próximos passos recomendados

1. Investigar dgl1905 e definir a política para arquivos multi-seção sem profundidade composta.
2. Criar testes automatizados para C1, C2, multi-energia e modos de QF.
3. Adicionar guarda para ausência de Rep0 e validação de dtypes.
4. Vetorizar `compute_flags` e medir desempenho com dgl1905.
5. Concluir o relatório PDF por testemunho e integrá-lo à interface.
6. Discutir com a equipe a política para ausência de réplicas e exportação de Rep1/Rep2.
7. Testar o empacotamento no Ubuntu.
