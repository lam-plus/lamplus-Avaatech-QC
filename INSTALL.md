# Instalacao no Ubuntu

Este guia mostra como instalar e preparar o projeto em uma maquina Ubuntu.

## Requisitos

- Ubuntu 22.04+ (ou similar)
- Python 3.10+ instalado no conda/Miniforge
- `pip` e `venv`

## 1) Sair do `base` automaticamente no terminal

Se o seu terminal abre com `(base)`, desative a ativacao automatica uma vez:

```bash
conda config --set auto_activate_base false
```

Depois feche e abra o terminal de novo. Quando quiser usar o conda, ative o ambiente manualmente.

## 2) Instalar dependencias de sistema

```bash
sudo apt update
sudo apt install -y python3 python3-pip
```

## 3) Entrar na pasta do projeto

```bash
cd /caminho/para/lamplus-Avaatech-QC
```

## 4) Criar e ativar o ambiente virtual

Use o Python do conda para criar o `.venv` do projeto:

```bash
/home/abelem/miniforge3/bin/python -m venv .venv
source .venv/bin/activate
```

## 5) Atualizar o pip e instalar dependencias

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 6) Verificar instalacao

```bash
python -m pip list
```

## 7) Desativar o ambiente virtual (quando terminar)

```bash
deactivate
```

## Observacoes

- Sempre ative o ambiente virtual antes de executar o projeto.
- Se o terminal ainda mostrar `(base)`, rode `conda deactivate` antes de ativar o `.venv`.
- Em novas sessoes do terminal, rode novamente:

```bash
source .venv/bin/activate
```
