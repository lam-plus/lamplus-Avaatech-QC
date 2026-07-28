# Como instalar o LAM+ Core QC no seu computador

Este guia foi escrito para quem **nunca usou um terminal, nunca instalou um programa de programação e não sabe o que é "git", "venv" ou "pip"**. Vamos explicar cada palavra estranha antes de usar.

Não se preocupe: você não vai "quebrar" o computador seguindo estes passos. Se algo der errado ou não aparecer exatamente como está descrito aqui, **pare, copie a mensagem de erro (ou tire um print da tela) e mande para o Andre ou o Igor**. Ninguém espera que você resolva isso sozinho(a).

O guia tem duas versões: uma para **Windows** e uma para **Ubuntu/Linux**. Vá direto para a seção do seu sistema.

---

## Antes de começar: algumas palavras que vão aparecer

- **Terminal**: é uma janela onde você digita comandos em vez de clicar em botões. Parece assustador, mas aqui você só vai copiar e colar (ou digitar) algumas linhas, uma de cada vez.
- **Python**: a linguagem de programação em que este programa foi escrito. Precisamos instalá-la no computador antes de tudo.
- **Ambiente virtual (venv)**: pense nisso como **uma caixinha separada, só para este programa**. Tudo o que ele precisar instalar fica guardado dentro dessa caixinha, sem misturar com outras coisas do seu computador. Ela vai se chamar `.venv` e vai morar dentro da pasta do projeto.
- **pip**: o "instalador de peças". É ele quem baixa e instala, dentro da caixinha (`.venv`), tudo o que o programa precisa para funcionar.
- **Atalho**: depois de fazer a instalação uma única vez, você vai ter um ícone na área de trabalho para abrir o programa com um duplo clique, como qualquer outro programa. Você só vai precisar do terminal nesta instalação inicial.

Cada passo abaixo diz **o que o comando faz** antes de mostrar o comando em si, e **o que você deve ver na tela** depois de rodá-lo.

---

# Instalação no Windows

## Passo 1 — Coloque a pasta do projeto no computador

Você deve ter recebido (do Andre ou do Igor) um link ou uma pasta compartilhada com o projeto "LAM+ Core QC". Baixe/copie essa pasta inteira para um lugar de fácil acesso no seu computador, por exemplo dentro de **Documentos**.

- Se você recebeu um link do GitHub: clique no botão verde **"Code"** e depois em **"Download ZIP"**. Depois de baixar, clique com o botão direito no arquivo `.zip` e escolha **"Extrair Tudo..."** (Extract All).
- Se você recebeu uma pasta compartilhada (Google Drive, pendrive, etc.): copie a pasta inteira para o seu computador normalmente, como copiaria uma pasta de fotos.

No final deste passo, você deve ter uma pasta chamada algo como `lamplus-Avaatech-QC`, com vários arquivos dentro (incluindo um chamado `qc_avaatech.py`).

## Passo 2 — Abra o PowerShell

O PowerShell é o terminal do Windows.

1. Aperte a tecla **Windows** (aquela com o logo do Windows, entre Ctrl e Alt).
2. Digite `PowerShell`.
3. Vai aparecer um ícone escrito **"Windows PowerShell"** — aperte **Enter**.

Uma janela azul (ou preta) vai abrir, com um texto e um cursor piscando. É aqui que vamos digitar os comandos.

## Passo 3 — Entre na pasta do projeto

Precisamos dizer ao PowerShell para "ficar dentro" da pasta do projeto. O comando para mudar de pasta é `cd` (de "change directory"), seguido do caminho da pasta.

Em vez de digitar o caminho todo, faça assim:

1. Clique dentro da janela do PowerShell e digite `cd ` (as letras "c", "d" e um espaço depois — **não aperte Enter ainda**).
2. Abra o Explorador de Arquivos, encontre a pasta do projeto (a do Passo 1), e **arraste essa pasta para dentro da janela do PowerShell**, soltando-a ali. O caminho completo da pasta vai aparecer sozinho, colado depois do `cd `.
3. Agora sim, aperte **Enter**.

O resultado vai ficar parecido com este exemplo (o seu caminho vai ser diferente — não digite este exemplo, ele é só uma ilustração):

```powershell
cd "C:\Users\SeuNome\Documents\lamplus-Avaatech-QC"
```

> Depois de apertar Enter, a linha do terminal vai mudar para mostrar essa pasta (algo como `PS C:\Users\SeuNome\Documents\lamplus-Avaatech-QC>`). Isso significa que deu certo.

## Passo 4 — Confira se o Python está instalado

```powershell
python --version
```

> **Se aparecer algo como `Python 3.11.5`**: ótimo, o Python já está instalado — pule para o Passo 5.
>
> **Se aparecer uma mensagem de erro** (algo como "python não é reconhecido..."), o Python ainda não está instalado. Vá até [python.org/downloads](https://python.org/downloads) no seu navegador, clique no botão amarelo para baixar, e execute o instalador. **Importante:** na primeira tela do instalador, marque a caixinha **"Add python.exe to PATH"** antes de clicar em "Install Now". Depois de instalar, **feche o PowerShell e abra de novo** (Passo 2), entre na pasta de novo (Passo 3) e repita este Passo 4.

## Passo 5 — Crie a "caixinha" do programa (o ambiente virtual)

Este comando cria a pasta `.venv` — a caixinha separada mencionada lá em cima.

```powershell
python -m venv .venv
```

> A janela pode ficar alguns segundos sem mostrar nada e depois voltar ao normal — isso é esperado, é rápido. Não vai aparecer nenhuma mensagem se der certo.

## Passo 6 — Ative a caixinha

"Ativar" significa: a partir de agora, os próximos comandos vão instalar coisas *dentro* da caixinha `.venv`, e não espalhadas pelo resto do computador.

```powershell
.venv\Scripts\Activate.ps1
```

> Se der certo, o começo da linha do terminal vai ganhar um `(.venv)` na frente, assim: `(.venv) PS C:\...>`.
>
> **Se aparecer uma mensagem de erro falando em "execution policies" ou "scripts is disabled"**, é uma trava de segurança do Windows contra scripts desconhecidos — bem comum na primeira vez. Cole o comando abaixo, aperte Enter, e quando ele perguntar algo digite `S` (de "Sim") e aperte Enter de novo. Depois repita o comando deste Passo 6.
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

## Passo 7 — Instale as peças que o programa precisa

```powershell
python -m pip install --upgrade pip
```

> Vai aparecer uma linha dizendo que o pip foi atualizado. Normal.

Agora o comando principal, que baixa e instala tudo o que o programa usa (isso inclui bibliotecas de cálculo, gráficos, e a interface visual):

```powershell
python -m pip install -r requirements.txt
```

> **Isso demora um pouco (alguns minutos, dependendo da internet) e vai aparecer bastante texto na tela — várias linhas com nomes de pacotes, barras de progresso, etc. Isso é totalmente normal, é só aguardar até a linha de comando voltar a aparecer livre**, sem nada rodando. Não fique preocupado(a) com a quantidade de texto.

## Passo 8 — Teste o programa

```powershell
python iniciar.py
```

> Depois de alguns segundos, o seu navegador de internet deve abrir sozinho numa aba mostrando a tela do "LAM+ Core QC". Se o navegador não abrir sozinho, abra-o manualmente e acesse o endereço `http://localhost:8501`.
>
> A janela do PowerShell precisa continuar aberta enquanto você usa o programa — é ela que está "rodando" o programa por trás. Você pode deixá-la minimizada. Para fechar o programa, feche essa janela do PowerShell (ou feche a aba do navegador e depois a janela do PowerShell).

Se a tela do programa apareceu certinho, a instalação deu certo! Só falta um último passo para facilitar o uso no dia a dia.

## Passo 9 — Crie o atalho na área de trabalho

Ainda na mesma janela do PowerShell (com o `(.venv)` na frente):

```powershell
python setup_shortcut.py
```

> Vai aparecer uma mensagem dizendo que um ícone e um atalho foram criados. Agora deve existir um ícone chamado **"LAM+ Core QC"** na sua área de trabalho.

---

# Instalação no Ubuntu/Linux

## Passo 1 — Coloque a pasta do projeto no computador

Você deve ter recebido (do Andre ou do Igor) um link ou uma pasta compartilhada com o projeto "LAM+ Core QC". Baixe/copie essa pasta inteira para um lugar de fácil acesso, por exemplo dentro de **Documentos**.

- Se você recebeu um link do GitHub: clique no botão verde **"Code"** e depois em **"Download ZIP"**. Depois de baixar, clique com o botão direito no arquivo `.zip`, no gerenciador de arquivos, e escolha **"Extrair Aqui"** (Extract Here).
- Se você recebeu uma pasta compartilhada: copie a pasta inteira para o seu computador normalmente.

No final deste passo, você deve ter uma pasta chamada algo como `lamplus-Avaatech-QC`, com vários arquivos dentro (incluindo um chamado `qc_avaatech.py`).

## Passo 2 — Abra o Terminal

No Ubuntu, aperte ao mesmo tempo as teclas **Ctrl + Alt + T**. Uma janela escura com texto vai abrir — é o terminal.

## Passo 3 — Entre na pasta do projeto

O comando para mudar de pasta é `cd` (de "change directory"), seguido do caminho da pasta.

Em vez de digitar o caminho todo, faça assim:

1. Clique dentro da janela do terminal e digite `cd ` (as letras "c", "d" e um espaço depois — **não aperte Enter ainda**).
2. Abra o gerenciador de arquivos (Nautilus/Files), encontre a pasta do projeto (a do Passo 1), e **arraste essa pasta para dentro da janela do terminal**, soltando-a ali. O caminho completo da pasta vai aparecer sozinho, colado depois do `cd `.
3. Agora aperte **Enter**.

O resultado vai ficar parecido com este exemplo (o seu caminho vai ser diferente — não digite este exemplo, ele é só uma ilustração):

```bash
cd /home/seunome/Documentos/lamplus-Avaatech-QC
```

> Depois de apertar Enter, a linha do terminal vai mudar para mostrar essa pasta. Isso significa que deu certo.

## Passo 4 — Instale o Python e as ferramentas necessárias

No Ubuntu o Python normalmente já vem instalado, mas precisamos garantir que duas peças extras (`venv` e `pip`) também estejam presentes. Rode os comandos abaixo, um de cada vez.

Primeiro, atualiza a lista de programas disponíveis:

```bash
sudo apt update
```

> Vai pedir a sua senha do Ubuntu (a mesma de fazer login no computador). **Ao digitar, nenhum caractere vai aparecer na tela — nem bolinhas, nem asteriscos.** Isso é normal e é assim mesmo por segurança. Digite a senha "às cegas" e aperte Enter.

Agora instala o Python e as peças que faltam:

```bash
sudo apt install python3 python3-venv python3-pip
```

> Vai aparecer bastante texto e, em algum momento, uma pergunta do tipo `Do you want to continue? [Y/n]` — digite `Y` (ou apenas aperte Enter) e aguarde terminar.

## Passo 5 — Crie a "caixinha" do programa (o ambiente virtual)

Este comando cria a pasta `.venv` — uma caixinha separada só para este programa, para não misturar com outros programas do computador.

```bash
python3 -m venv .venv
```

> A janela pode ficar alguns segundos sem mostrar nada e depois voltar ao normal — isso é esperado. Não vai aparecer nenhuma mensagem se der certo.

## Passo 6 — Ative a caixinha

```bash
source .venv/bin/activate
```

> Se der certo, o começo da linha do terminal vai ganhar um `(.venv)` na frente.

## Passo 7 — Instale as peças que o programa precisa

```bash
python -m pip install --upgrade pip
```

> Vai aparecer uma linha dizendo que o pip foi atualizado. Normal.

Agora o comando principal, que baixa e instala tudo o que o programa usa:

```bash
python -m pip install -r requirements.txt
```

> **Isso demora um pouco (alguns minutos, dependendo da internet) e vai aparecer bastante texto na tela. Isso é normal — só aguarde até a linha de comando voltar a aparecer livre**, sem nada rodando.

## Passo 8 — Teste o programa

```bash
python iniciar.py
```

> Depois de alguns segundos, o seu navegador de internet deve abrir sozinho numa aba mostrando a tela do "LAM+ Core QC". Se não abrir sozinho, abra-o manualmente e acesse `http://localhost:8501`.
>
> A janela do terminal precisa continuar aberta enquanto você usa o programa. Para fechar o programa, feche essa janela do terminal (ou aperte `Ctrl + C` dentro dela).

Se a tela do programa apareceu certinho, a instalação deu certo!

## Passo 9 — Crie o atalho

Ainda no mesmo terminal (com o `(.venv)` na frente):

```bash
python setup_shortcut.py
```

> Vai aparecer uma mensagem dizendo que um atalho foi criado no menu de aplicativos e, se você tiver uma pasta "Área de Trabalho"/"Desktop", também um ícone lá.
>
> **No Ubuntu, ícones novos costumam vir "bloqueados" por segurança na primeira vez.** Se ao clicar no ícone da área de trabalho não acontecer nada, ou aparecer um aviso, clique com o botão direito nele e procure uma opção parecida com **"Permitir Execução"** / **"Allow Launching"** / **"Confiar e Executar"** (o nome muda um pouco dependendo da versão do Ubuntu). Depois disso, o duplo clique passa a funcionar normalmente.

---

## Usando o programa no dia a dia

Depois de terminar os passos acima **uma única vez**, você não precisa mais abrir terminal nenhum. Sempre que quiser usar o LAM+ Core QC:

1. Dê um duplo clique no ícone **"LAM+ Core QC"** na área de trabalho (ou procure por "LAM+ Core QC" no menu de aplicativos, no Ubuntu).
2. Uma janela preta vai abrir por trás (é normal, é ela que roda o programa — pode minimizar) e o navegador vai abrir sozinho com a tela do programa.
3. Quando terminar de usar, feche a janela preta/terminal para desligar o programa.

Você só vai precisar repetir os passos de instalação se trocar de computador, ou se o Andre/Igor pedirem para atualizar o programa.

---

## Se algo der errado

Isso é completamente normal — instalar qualquer programa pela primeira vez pode ter percalços, e cada computador é um pouco diferente do outro.

**Não tente adivinhar ou "forçar" — copie a mensagem de erro (ou tire um print da tela inteira) e envie para o Andre ou o Igor.** Quanto mais detalhe você mandar (em qual passo estava, o que apareceu na tela), mais rápido eles conseguem te ajudar.
