# Plano de Ação — LAM+ Core QC V2

## Objetivo

Construir uma versão V2 simplificada do LAM+ Core QC, usando a pasta `LEGACY/` como referência técnica e metodológica, sem criar dependência de runtime entre a nova implementação e o código legado.

A V2 deve priorizar:

- arquitetura simples;
- poucos componentes;
- regras metodológicas explícitas;
- código testável;
- menor custo de manutenção;
- comparação controlada com a versão anterior;
- preservação da rastreabilidade científica.

---

## Princípios de execução

1. Não implementar toda a V2 em uma única tarefa.
2. Dividir o trabalho em etapas pequenas e auditáveis.
3. Usar `LEGACY/` como referência, nunca como dependência.
4. Revisar o diff após cada etapa.
5. Executar testes antes de avançar.
6. Não permitir que o Codex tome decisões metodológicas sem validação.
7. Distinguir claramente:
   - comportamento preservado;
   - comportamento simplificado;
   - comportamento deliberadamente removido;
   - correção de bug;
   - mudança metodológica.

---

## Papel do Codex

O Codex será usado para:

- ler o repositório;
- consultar a implementação em `LEGACY/`;
- criar e editar arquivos;
- executar comandos;
- rodar testes;
- comparar resultados;
- corrigir falhas de implementação;
- apresentar diffs e relatórios técnicos.

O Codex não deve decidir sozinho:

- thresholds finais;
- regras científicas;
- política para ausência de réplicas;
- interpretação do Argônio;
- critérios de rejeição;
- equivalência entre resultados da V1 e da V2;
- se uma divergência é bug ou mudança metodológica legítima.

---

## Papel da revisão humana

A revisão humana deve confirmar:

- se a implementação corresponde ao protocolo;
- se os resultados são cientificamente defensáveis;
- se os módulos mantêm sua interpretação correta;
- se dados faltantes não são mascarados;
- se a simplificação não remove controles essenciais;
- se as diferenças em relação à LEGACY são intencionais.

---

# Etapas de implementação

## Etapa 1 — Estrutura inicial e contratos

### Objetivo

Criar o esqueleto da V2 sem implementar ainda toda a lógica científica.

### Entregas

- estrutura mínima de arquivos;
- funções públicas definidas;
- contratos de entrada e saída;
- constantes centrais;
- enums ou estados de QC;
- estrutura inicial de testes;
- documentação curta da arquitetura.

### Estrutura sugerida

```text
qc_core.py
qc_config.py
qc_io.py
qc_reports.py
qc_avaatech.py
tests/
```

### Validação

- imports funcionando;
- nenhum módulo importado de `LEGACY/`;
- testes básicos de importação;
- interfaces públicas claras.

---

## Etapa 2 — Leitura e validação de dados

### Objetivo

Implementar a ingestão dos workbooks Avaatech.

### Entregas

- leitura de uma ou várias abas;
- detecção de energia;
- validação das colunas por energia;
- seleção de `Rep0`;
- detecção de réplicas;
- tratamento de abas desconhecidas;
- mensagens claras para arquivos inválidos;
- separação entre módulo ausente e dado faltante.

### Casos de teste

- arquivo 10 kV;
- arquivo 10/30 kV;
- arquivo 10/30/50 kV;
- ausência de `Rep0`;
- coluna crítica ausente;
- coluna numérica lida como texto;
- aba com nome inesperado;
- módulo não aplicável em 50 kV.

---

## Etapa 3 — Implementação de QC1 a QC3

### Objetivo

Implementar os três módulos instrumentais básicos.

### Entregas

- QC1 — Instrument Stability;
- QC2 — Coherent Scatter;
- QC3 — Incoherent Scatter;
- z-score robusto;
- estados OK / ALERT / CRITICAL;
- tratamento explícito de NaN;
- causas associadas por linha.

### Pontos metodológicos a confirmar

- uso de Throughput e Argônio em QC1;
- forma de combinar os dois sinais;
- thresholds de alerta e crítico;
- comportamento quando Argônio não está disponível.

### Validação

- testes unitários;
- comparação com arquivos reais;
- confirmação de que NaN nunca vira OK;
- comparação com saídas da LEGACY.

---

## Etapa 4 — Implementação de QC4 e QC5

### Objetivo

Implementar anomalias locais e reprodutibilidade.

### Entregas

- QC4 — Rolling QC;
- QC5 — Replicates;
- janela móvel;
- persistência temporal, se mantida;
- casamento de réplicas por chave física correta;
- cálculo de RPD;
- tratamento de média zero;
- estados discretos.

### Pontos metodológicos a confirmar

- tamanho da janela;
- uso ou não de persistência;
- variáveis usadas no rolling;
- thresholds de RPD;
- política para ausência de réplica.

### Testes obrigatórios

- reprodução do achado C1;
- média zero no RPD;
- ausência de réplica;
- múltiplas seções;
- anomalia isolada;
- anomalia persistente.

---

## Etapa 5 — Integração dos estados e Quality Flags

### Objetivo

Integrar QC1–QC5 e gerar o resultado final.

### Entregas

- contagem de ALERT e CRITICAL;
- QF0 a QF3;
- QF indeterminado separado;
- causa principal;
- evidências secundárias;
- indicação de revisão;
- resumo por energia.

### Regra inicial proposta

| QF | Critério |
|---|---|
| QF0 | nenhum ALERT e nenhum CRITICAL |
| QF1 | um ALERT |
| QF2 | dois ou três ALERTs, ou um CRITICAL |
| QF3 | dois ou mais CRITICALs, ou quatro ou mais ALERTs |

### Validação

- testes com combinações sintéticas de estados;
- NaN crítico produz indeterminado;
- módulos não aplicáveis não geram penalidade;
- comparação com o protocolo do Igor;
- comparação com resultados da LEGACY.

---

## Etapa 6 — Saídas e interface mínima

### Objetivo

Criar produtos simples e utilizáveis.

### Entregas

- Excel com abas preservadas;
- colunas originais mantidas;
- colunas QC adicionadas;
- coloração simples;
- aba de intervalos;
- resumo textual;
- interface mínima em Streamlit;
- upload;
- processamento;
- visualização do resumo;
- download.

### Fora do escopo inicial

- PDF complexo;
- PCA;
- clustering;
- Mahalanobis;
- múltiplos modos de QF;
- excesso de opções na UI;
- empacotamento sofisticado antes da estabilização.

---

## Etapa 7 — Testes e comparação com a LEGACY

### Objetivo

Demonstrar que a V2 é confiável e que as diferenças são compreendidas.

### Entregas

- suíte automatizada;
- testes para C1 e C2;
- testes multi-energia;
- testes de dados faltantes;
- comparação com arquivos reais;
- tabela de diferenças V1 × V2;
- registro de divergências esperadas;
- benchmark básico.

### Arquivos prioritários

- `exemplo_dados_consolidados.xlsx`;
- `Dados Consolidados-ICCE3.xlsx`;
- `Dados Consolidados-OP42GC4.xlsx`;
- `Dados Consolidados-dgl1905.xlsx`;
- demais arquivos usados na validação da LEGACY.

### Critério de aceitação

Toda divergência deve ser classificada como:

- equivalente;
- correção de bug;
- simplificação deliberada;
- mudança metodológica;
- regressão.

---

# Estratégia de uso do Codex

## Forma recomendada

Para cada etapa:

1. enviar uma tarefa específica;
2. pedir plano antes da alteração;
3. permitir implementação;
4. exigir testes;
5. revisar o diff;
6. registrar o resultado;
7. só então avançar.

## Evitar

- “implemente toda a V2”;
- tarefas com muitas frentes simultâneas;
- mudanças de metodologia e arquitetura no mesmo prompt;
- refatoração sem testes;
- aceitação automática de resultados.

---

# Controle de consumo

Para reduzir o consumo de créditos:

- trabalhar em etapas curtas;
- evitar pedir releitura completa da `LEGACY/` a cada tarefa;
- apontar arquivos específicos;
- pedir diffs objetivos;
- não repetir validações já concluídas;
- usar este chat para decisões metodológicas e revisão de prompts;
- usar o Codex para alterações reais no repositório e execução de testes.

---

# Critérios de conclusão da V2 inicial

A V2 inicial será considerada concluída quando:

- QC1–QC5 estiverem implementados;
- o QF por contagem estiver operacional;
- dados faltantes não puderem virar OK;
- workbooks multi-energia forem processados;
- módulos não aplicáveis forem tratados corretamente;
- o Excel de saída preservar os dados originais;
- a suíte de testes estiver passando;
- C1 e C2 estiverem cobertos por testes;
- arquivos reais forem processados sem falhas críticas;
- a V2 não importar nada de `LEGACY/`;
- as divergências em relação à versão antiga estiverem documentadas;
- `DEVELOPMENT.md` e `TODO.md` refletirem o estado real da V2.
