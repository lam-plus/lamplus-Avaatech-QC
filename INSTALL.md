# Instalacao no Ubuntu

Este guia mostra como instalar e preparar o projeto em uma maquina Ubuntu.

## Requisitos

- Ubuntu 22.04+ (ou similar)
- Python 3.10+ instalado
- `pip` e `venv`

## 1) Instalar dependencias de sistema

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

## 2) Entrar na pasta do projeto

```bash
cd /caminho/para/lamplus-Avaatech-QC
```

## 3) Criar e ativar o ambiente virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 4) Atualizar o pip e instalar dependencias

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 5) Verificar instalacao

```bash
python -m pip list
```

## 6) Desativar o ambiente virtual (quando terminar)

```bash
deactivate
```

## Observacoes

- Sempre ative o ambiente virtual antes de executar o projeto.
- Em novas sessoes do terminal, rode novamente:

```bash
source .venv/bin/activate
```
