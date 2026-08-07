# LAM+ Core QC — nova refatoração

Este diretório é a área de desenvolvimento ativo da nova versão do LAM+ Core
QC. A implementação estável anterior foi preservada integralmente em
[`LEGACY/`](LEGACY/README.md).

## Estado atual

A nova implementação ainda está em fase de estruturação. O trabalho deve
seguir:

- [`TODO.md`](TODO.md), para pendências, decisões abertas e próximos passos;
- [`DEVELOPMENT.md`](DEVELOPMENT.md), para arquitetura, decisões técnicas e
  histórico de validações;
- [`src/`](src/README.md), para o código da nova versão.

Os arquivos Excel em `data/` permanecem na raiz como dados de validação
compartilhados. Os relatórios já gerados em `data/reports/` são artefatos
históricos e não fazem parte da implementação.

## Funcionalidades

- Upload de workbook Avaatech (.xlsx), validação, execução do pipeline QC1-QC5
  e exportação dos resultados em Excel;
- resumo/sumário visual por energia e download do resumo em texto;
- interface bilíngue (EN/PT, EN como padrão);
- **trilha de auditoria (aba "Histórico")** — registra localmente, em
  `data/audit.db` (SQLite), quem rodou o QC, qual arquivo e a distribuição de
  QF resultante. Essa funcionalidade **requer instalação local com um
  diretório `data/` gravável**; pode ser desligada a qualquer momento pelo
  toggle "Enable audit log"/"Ativar registro de auditoria" na sidebar. Em
  ambientes hospedados (ex. Streamlit Community Cloud), o armazenamento local
  costuma ser somente leitura ou efêmero — **os dados de auditoria não são
  persistidos entre sessões** nesses ambientes, mesmo com o toggle ligado.

## Versão estável anterior

Para executar, consultar, comparar ou recuperar a aplicação anterior, use as
instruções em [`LEGACY/README.md`](LEGACY/README.md). Novas funcionalidades
não devem ser implementadas ali.

