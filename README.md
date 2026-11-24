# Case técnico — precatórios

Análise de um fluxo de importação de precatórios: diagnóstico dos problemas nos
dados/processo, limpeza dos arquivos brutos em Python e propostas de prevenção.

## Estrutura

```
dados/                    arquivos brutos do tribunal (não alterar)
schema.sql                esquema atual do banco
loader.py                 leitura tolerante de CSV/JSON
norm.py                   normalização de processo, nome, valor e data
tests/                    testes das duas camadas acima
requirements.txt          dependências
ENUNCIADO.md              enunciado do case
DOCUMENTACAO_TRIBUNAL.md  leiaute dos arquivos de integração
```

## Requisitos

- Python 3.10+
- pandas, pytest (`pip install -r requirements.txt`)

## Como rodar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python loader.py      # lê e imprime os arquivos de dados/
pytest                # roda a suíte de testes
```

## Testes

Os testes cobrem as duas camadas de entrada:

- `tests/test_loader.py` — leitura de CSV (UTF-8/latin-1, vírgula e ponto e
  vírgula, BOM, espaços) e JSON.
- `tests/test_norm.py` — normalização do número CNJ, de nomes, de valores
  monetários (incluindo formato brasileiro) e de datas (com conversão de fuso
  para America/Sao_Paulo).

## Uso de IA

A ser preenchido: quais ferramentas foram usadas e como o resultado foi conferido.
