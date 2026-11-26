# Case técnico — precatórios

Análise de um fluxo de importação de precatórios: diagnóstico dos problemas nos
dados/processo, limpeza dos arquivos brutos em Python e propostas de prevenção.

## Estrutura

```
dados/                    arquivos brutos do tribunal (não alterar)
schema.sql                esquema atual do banco
main.py                   ponto de entrada: executa a limpeza completa
src/loader.py             leitura tolerante de CSV/JSON
src/norm.py               normalização de processo, nome, valor e data
src/validacao.py          validação e classificação dos eventos de pagamento
src/prazo.py              regra constitucional de prazo (2 de abril)
src/limpeza.py            limpeza dos arquivos e geração do relatório
tests/                    testes das camadas acima
DIAGNOSTICO.md            diagnóstico, prevenção e dúvidas
migrations/001_prevencao.sql  correções de schema e controle de importação
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

python main.py        # executa a limpeza e gera a pasta saida/
pytest                # roda a suíte de testes
```

## Saída

`python main.py` grava em `saida/` as bases limpas (`*_limpos.json` e
`*_limpos.csv`), o `relatorio_limpeza.json` e os registros descartados e
pendentes, com o motivo de cada um.

## Banco

O schema atual está em `schema.sql`. As correções propostas estão em
`migrations/001_prevencao.sql`, que deve ser aplicada em transação e só depois
de revisar as duplicatas existentes.

```bash
psql -h localhost -U postgres -d precatorios -v ON_ERROR_STOP=1 \
  -f migrations/001_prevencao.sql
```

O diagnóstico, a prevenção e as dúvidas estão em `DIAGNOSTICO.md`.

## Testes

Os testes cobrem as camadas de entrada e validação:

- `tests/test_loader.py` — leitura de CSV (UTF-8/latin-1, vírgula e ponto e
  vírgula, BOM, espaços) e JSON.
- `tests/test_norm.py` — normalização do número CNJ, de nomes, de valores
  monetários (incluindo formato brasileiro) e de datas (com conversão de fuso
  para America/Sao_Paulo).
- `tests/test_validacao.py` — validação de um evento (campos obrigatórios, tipo,
  valor positivo, timestamps) e classificação em importáveis, corrigidos,
  descartados e pendentes, incluindo duplicatas idênticas e divergentes.
- `tests/test_limpeza.py` — mapeamento dos campos reais de cada arquivo,
  deduplicação, recálculo de prazo no hub, reconciliação de processos e
  gravação dos artefatos de saída.
- `tests/test_prazo.py` — regra do prazo constitucional, incluindo a data de
  corte de 2 de abril.

## Uso de IA

- Ferramentas: Opencode (geração de sugestões de código e testes) e ChatGPT
  (arquitetura do projeto).
