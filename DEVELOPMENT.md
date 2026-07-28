# Desenvolvimento — LAM+ Core QC V2

## 1. Objetivo da V2

A V2 será uma implementação mais simples, modular e auditável do controle de
qualidade de aquisição de dados do Avaatech XRF Core Scanner.

A prioridade desta versão é:

- manter o foco no controle de qualidade da aquisição;
- reduzir o número de opções configuráveis;
- diminuir o acoplamento entre leitura, cálculo, interface e exportação;
- produzir código mais fácil de compreender e testar;
- oferecer uma saída direta e rastreável;
- simplificar a manutenção.

A V2 começa com um núcleo pequeno e bem definido. Funcionalidades adicionais
só deverão ser consideradas depois que esse núcleo estiver estabilizado,
testado com dados reais e documentado.

## 2. Relação com `LEGACY/`

`LEGACY/` preserva a implementação estável anterior, sua documentação técnica,
suas decisões metodológicas e seu histórico de validações. Ela serve para
consulta, comparação de resultados e recuperação do comportamento anterior.

A V2 pode consultar conceitos, regras e trechos da implementação legada durante
o desenvolvimento. Entretanto:

- a V2 não pode importar módulos de `LEGACY/` em runtime;
- `LEGACY/` é referência, não dependência;
- nenhum caminho da V2 deve apontar para recursos internos de `LEGACY/`;
- qualquer comportamento reaproveitado deve ser implementado explicitamente
  na V2;
- testes da V2 devem conseguir executar sem adicionar `LEGACY/` ao
  `PYTHONPATH`.

Essa separação permite evoluir a nova arquitetura sem alterar o comportamento
histórico preservado.

## 3. Escopo funcional inicial

O núcleo inicial seguirá uma proposta simplificada baseada no protocolo do
Igor:

- **QC1 — Instrument Stability:** estabilidade instrumental;
- **QC2 — Coherent Scatter:** avaliação do espalhamento coerente;
- **QC3 — Incoherent Scatter:** avaliação do espalhamento incoerente;
- **QC4 — Rolling QC:** detecção de anomalias locais;
- **QC5 — Replicates:** avaliação da reprodutibilidade entre réplicas;
- atribuição de QF por contagem dos estados dos módulos;
- processamento de workbooks multi-energia;
- exportação dos resultados em Excel;
- geração de resumo simples.

O núcleo inicial não incluirá PCA. Também não oferecerá múltiplas filosofias
concorrentes para cálculo de QF nem excesso de opções metodológicas na
interface.

## 4. Princípios de implementação

### 4.1 Organização

- Manter uma única fonte de verdade para configurações, limiares e estados.
- Preferir funções pequenas, com entradas e saídas explícitas.
- Separar leitura, validação, cálculo, classificação e exportação.
- Evitar estado global mutável e dependências implícitas da interface.
- Cobrir as regras científicas e os casos de borda com testes automatizados.

### 4.2 Dados faltantes e aplicabilidade

- Emitir mensagens claras quando dados obrigatórios estiverem ausentes.
- Nunca tratar `NaN` como estado OK.
- Representar dados indeterminados separadamente dos estados QF0–QF3.
- Tratar módulos não aplicáveis a uma energia como neutros, sem confundi-los
  com dados críticos ausentes.
- Tornar explícito quais módulos e variáveis participaram da classificação.

### 4.3 Integridade e rastreabilidade

- Não alterar automaticamente as colunas ou os valores originais.
- Acrescentar resultados de QC de forma identificável.
- Registrar a causa principal e as evidências que sustentam cada flag.
- Documentar decisões metodológicas e mudanças de comportamento.
- Manter resultados reproduzíveis para uma mesma entrada e configuração.

## 5. Estrutura proposta

Estrutura inicial sugerida:

```text
qc_core.py
qc_config.py
qc_io.py
qc_reports.py
qc_avaatech.py
tests/
```

Responsabilidades previstas:

- `qc_config.py`: energias, variáveis, limiares e estados;
- `qc_io.py`: leitura do workbook, detecção de energia e validação estrutural;
- `qc_core.py`: cálculos QC1–QC5 e integração dos estados;
- `qc_reports.py`: Excel e resumo simples;
- `qc_avaatech.py`: interface mínima;
- `tests/`: testes unitários, sintéticos e de integração.

Essa estrutura é uma proposta e ainda não representa código implementado. Uma
mudança nela deve preservar a separação de responsabilidades.

## 6. Contrato da V2

A V2 deverá:

1. ler workbooks exportados pelo Avaatech;
2. detectar a energia de cada aba suportada;
3. validar as colunas necessárias para aquela energia;
4. selecionar as medições `Rep0`;
5. usar réplicas adicionais quando estiverem disponíveis;
6. devolver um estado explícito para cada módulo QC aplicável;
7. produzir QF0, QF1, QF2 ou QF3 por contagem dos estados;
8. marcar dados indeterminados em uma categoria separada;
9. registrar causa principal e evidências de apoio;
10. exportar os resultados sem alterar as colunas originais.

Entradas inválidas devem produzir mensagens acionáveis. A ausência legítima de
um módulo em determinada energia não deve penalizar o resultado, enquanto a
ausência de um dado obrigatório não pode resultar em OK.

## 7. Validação

A V2 deverá ser validada contra:

- os arquivos reais já usados para validar a versão em `LEGACY/`;
- resultados esperados definidos antes da implementação;
- casos sintéticos que isolem cada regra;
- testes de regressão para os achados críticos C1 e C2.

O teste de C1 deverá garantir que as réplicas sejam associadas por uma chave
física válida, sem depender de profundidades ausentes em `Rep1` ou `Rep2`.

O teste de C2 deverá garantir que um dado crítico ausente nunca seja
classificado como OK, independentemente da regra de agregação.

Também deverão existir testes multi-energia, testes de dados malformados e uma
comparação documentada entre os resultados da V2 e os resultados históricos.
Diferenças deliberadas deverão ser justificadas.

## 8. Fora do escopo inicial

Ficam fora do núcleo inicial:

- PCA;
- clustering;
- distância de Mahalanobis;
- relatório PDF complexo;
- múltiplos modos de QF;
- opções avançadas de rolling;
- interface excessivamente configurável;
- empacotamento sofisticado antes da estabilização do núcleo.

Esses itens poderão ser reavaliados após a conclusão dos critérios da primeira
versão funcional, sem criar dependência de runtime com `LEGACY/`.

