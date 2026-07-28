# TODO — LAM+ Core QC V2

Este arquivo contém somente o trabalho da V2 simplificada. O histórico e as
pendências da versão anterior estão em `LEGACY/TODO.md`.

## 1. Definições iniciais

- [ ] Confirmar o escopo da V2.
- [ ] Confirmar os módulos QC1–QC5.
- [ ] Confirmar as regras de QF por contagem.
- [ ] Confirmar o tratamento de QF indeterminado.
- [ ] Confirmar o formato de saída.
- [ ] Confirmar a estrutura de arquivos.

## 2. Núcleo do pipeline

- [ ] Criar a leitura multi-energia.
- [ ] Validar as colunas exigidas por energia.
- [ ] Selecionar as medições `Rep0`.
- [ ] Implementar QC1 — Instrument Stability.
- [ ] Implementar QC2 — Coherent Scatter.
- [ ] Implementar QC3 — Incoherent Scatter.
- [ ] Implementar QC4 — Rolling QC.
- [ ] Implementar QC5 — Replicates.
- [ ] Integrar os estados dos módulos.
- [ ] Calcular QF por contagem.
- [ ] Registrar a causa principal e as evidências.

## 3. Robustez

- [ ] Impedir que `NaN` seja classificado como OK.
- [ ] Testar a ausência de `Rep0`.
- [ ] Testar a ausência de réplicas adicionais.
- [ ] Testar média zero no cálculo de RPD.
- [ ] Testar módulos não aplicáveis a uma energia.
- [ ] Testar workbook com abas inesperadas.
- [ ] Testar tipos de dados inválidos.

## 4. Saída

- [ ] Exportar resultados em Excel.
- [ ] Preservar as colunas originais.
- [ ] Adicionar colunas de QC.
- [ ] Adicionar uma aba de intervalos sinalizados.
- [ ] Gerar um resumo simples.

## 5. Interface mínima

- [ ] Implementar upload de arquivo.
- [ ] Implementar seleção do arquivo de entrada.
- [ ] Executar o processamento.
- [ ] Exibir um resumo dos resultados.
- [ ] Disponibilizar o download.
- [ ] Manter opções avançadas fora da interface inicial.

## 6. Testes

- [ ] Criar testes unitários.
- [ ] Criar teste de regressão para C1.
- [ ] Criar teste de regressão para C2.
- [ ] Criar testes multi-energia.
- [ ] Comparar os resultados com arquivos reais.
- [ ] Executar um benchmark básico.

## 7. Critérios de conclusão da V2 inicial

- [ ] Todos os testes passam.
- [ ] Os resultados são reproduzíveis.
- [ ] O código é independente de `LEGACY/` em runtime.
- [ ] A documentação está atualizada.
- [ ] A V2 executa com sucesso nos arquivos reais selecionados.
- [ ] Não há regressões críticas conhecidas.

