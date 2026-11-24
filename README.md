# Case técnico — precatórios

Análise de um fluxo de importação de precatórios: diagnóstico dos problemas nos
dados/processo, limpeza dos arquivos brutos em Python e propostas de prevenção.

## Estrutura

```
dados/                  arquivos brutos do tribunal (não alterar)
schema.sql              esquema atual do banco
loader.py               leitura tolerante de CSV/JSON
requirements.txt        dependências
ENUNCIADO.md            enunciado do case
DOCUMENTACAO_TRIBUNAL.md  leiaute dos arquivos de integração
```

## Requisitos

- Python 3.10+
- pandas, pytest (`pip install -r requirements.txt`)

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python loader.py
```

## Uso de IA

A ser preenchido: quais ferramentas foram usadas e como o resultado foi conferido.
