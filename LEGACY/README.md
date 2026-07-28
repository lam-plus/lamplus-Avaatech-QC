# LAM+ Core QC — implementação legada

Esta pasta contém a implementação estável anterior à refatoração do
repositório. Ela é preservada para rastreabilidade, comparação de resultados
e recuperação da versão historicamente validada.

O desenvolvimento ativo ocorre na raiz do repositório. Novas funcionalidades
não devem ser adicionadas ao legado. Alterações nesta pasta devem se limitar a
correções críticas necessárias para manter a reprodutibilidade histórica.

## Como executar

Use Python 3.10 ou superior. A partir da raiz do repositório:

```powershell
cd LEGACY
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run qc_avaatech.py
```

No Linux:

```bash
cd LEGACY
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run qc_avaatech.py
```

Também é possível iniciar com `python iniciar.py`. Instruções mais detalhadas
estão em [`INSTALL.md`](INSTALL.md).

## Dependências e entry points

As dependências Python estão declaradas em
[`requirements.txt`](requirements.txt). Os principais pontos de entrada são:

- `qc_avaatech.py`: interface Streamlit;
- `iniciar.py`: inicializador local da interface;
- `qc_core.py`: API do pipeline de controle de qualidade, sem dependência da
  interface;
- `setup_shortcut.py`: criação de atalho local;
- `installer/build_exe.py`: geração do executável com PyInstaller.

Os recursos necessários permanecem ao lado do código em `assets/`,
`locales/` e `installer/`, preservando os caminhos relativos usados pela
aplicação e pelo empacotador.

## Documentação preservada

- [`README_PRE_REFACTOR.md`](README_PRE_REFACTOR.md): README original da
  aplicação estável;
- [`INSTALL.md`](INSTALL.md): instalação e operação detalhadas;
- [`CLAUDE.md`](CLAUDE.md): arquitetura, convenções e descrição técnica dos
  módulos;
- [`DEVELOPMENT.md`](DEVELOPMENT.md): arquitetura, decisões e histórico
  consolidado de achados e validações;
- [`TODO.md`](TODO.md): pendências e roadmap preservados da versão anterior;
- [`installer/README_BUILD.md`](installer/README_BUILD.md): processo de
  empacotamento.

## Limitações conhecidas

- o executável standalone foi validado no Windows, mas não no Ubuntu;
- a ausência de réplicas ainda recebe score neutro/perfeito, por decisão
  metodológica pendente;
- o fallback de `CompositeDepth (mm)` para `CoreDepth` pode ser inadequado em
  testemunhos multi-seção;
- `Dados Consolidados-dgl1905.xlsx` apresentou volume atípico de profundidades
  duplicadas e requer investigação antes do uso dos resultados;
- o relatório PDF completo por testemunho ainda não está integrado como uma
  função reutilizável da interface;
- alguns pontos de robustez, desempenho e cobertura automatizada permanecem
  registrados no [`TODO.md`](TODO.md) desta pasta.

Os arquivos de dados não foram duplicados nesta pasta. Quando necessários para
validação histórica, use os arquivos mantidos em `../data/`.
