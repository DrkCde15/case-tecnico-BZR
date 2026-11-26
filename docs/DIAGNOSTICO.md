# Diagnóstico, prevenção e dúvidas

Análise do fluxo de importação de precatórios descrito em `ENUNCIADO.md`, com
evidências nos arquivos de `dados/`, na documentação do tribunal e no
`schema.sql`. As correções automatizáveis estão em `src/limpeza.py`; o
resultado de uma execução fica em `saida/relatorio_limpeza.json`.

## Resumo

- Foram lidos 29 registros nas quatro fontes: 22 importáveis (14 com alguma
  correção), 1 descartado e 6 pendentes de decisão.
- Os números não batem com os do tribunal por três motivos principais:
  pagamentos duplicados por reprocessamento, eventos rejeitados em silêncio e
  divergências reais de conteúdo entre `tribunal.csv` e `hub.csv`.
- A documentação do tribunal (v2.1) não corresponde aos arquivos recebidos, e o
  schema atual não comporta o fluxo (não há idempotência nem resolução de
  conflito).

## Como a limpeza trata cada fonte

| Fonte | Registros | Importáveis | Corrigidos | Descartados | Pendentes |
|---|---:|---:|---:|---:|---:|
| `pagamentos.json` | 13 | 6 | 2 | 1 | 6 |
| `apresentacoes.json` | 6 | 6 | 2 | 0 | 0 |
| `tribunal.csv` | 5 | 5 | 5 | 0 | 0 |
| `hub.csv` | 5 | 5 | 5 | 0 | 0 |

Critérios aplicados:

- os arquivos de `dados/` nunca são alterados; a saída vai para `saida/`;
- cada registro é classificado em importável, corrigido, descartado ou pendente,
  sempre com o motivo registrado;
- duplicata idêntica é descartada; mesma chave com conteúdo diferente vira
  pendência, sem escolha automática;
- o prazo do hub é recalculado pela regra constitucional e a diferença é
  registrada;
- os processos são reconciliados entre tribunal, apresentações, hub e
  pagamentos.

## Diagnóstico

Ordenado do mais grave para o menos grave.

### 1. Crítico — Reprocessamento do mesmo arquivo duplica pagamentos

**Evidência.** `dados/pagamentos.json:11-17` e `dados/pagamentos.json:27-33`
trazem o mesmo `ev-002` com conteúdo idêntico. O fluxo prevê reexecutar o script
com o mesmo arquivo quando a importação falha (`ENUNCIADO.md:16`), e
`schema.sql:8-16` não tem nenhuma restrição única em `evento_id`.

**Impacto.** O valor do evento é somado duas vezes ao total pago do processo
`0012345-10.2019.8.26.0053` (R$ 2.500,50 a mais). Qualquer saldo, relatório ou
cobrança derivado desse total nasce errado.

**Causa e consequência.** É a causa raiz da divergência de valores: o script não
é idempotente e o banco aceita a repetição. A consequência é o total pago maior
que o do tribunal, sem nenhum sinal de erro.

**Tratamento na limpeza.** A segunda cópia é descartada com o motivo "Duplicata
idêntica de outro registro" em `saida/registros_descartados.json`.

### 2. Crítico — Falhas de importação são silenciosas

**Evidência.** O fluxo determina que o script ignora o evento e segue, sem
avisar ninguém (`ENUNCIADO.md:19`). Na prática, 6 dos 13 eventos de pagamento
ficaram pendentes: `ev-001` em duas versões (`pagamentos.json:3-9` e `:67-73`),
`ev-004` com valor nulo (`:37`), `ev-007` com tipo `estorno` (`:63`), `ev-009`
com valor negativo (`:85`) e `ev-010` com processo vazio (`:92`).

**Impacto.** Até R$ 21.250,00 em pagamentos deixam de ser contabilizados,
considerando a versão mais recente do `ev-001`, sem contar o `ev-004` (valor
desconhecido) e o `ev-009` (negativo). A operação acredita que importou o
arquivo inteiro.

**Causa e consequência.** É consequência do fluxo do item 5 e da ausência de
log/alerta no script; vira causa de totais incompletos e de retrabalho manual.

**Tratamento na limpeza.** Os seis registros vão para
`saida/registros_pendentes.json`, com o motivo de cada um.

### 3. Alto — Divergências reais entre `tribunal.csv` e `hub.csv`

**Evidência.**

- `0023456-21.2020.8.26.0053`: valor R$ 30.000,00 em `tribunal.csv:3` e
  R$ 31.000,00 em `hub.csv:3` (R$ 1.000,00 de diferença).
- `0045678-43.2021.5.02.0011`: ente "União" em `tribunal.csv:5` e "Município de
  Santos" em `hub.csv:5`.
- `0056789-54.2017.4.03.6100`: existe em `hub.csv:6` e em
  `apresentacoes.json:19-21`, mas não em `tribunal.csv`.
- `0067890-65.2016.8.26.0053`: existe em `tribunal.csv:6`, em
  `apresentacoes.json:22-25` e no pagamento `ev-011` (`pagamentos.json:99-104`),
  mas não em `hub.csv`.

**Impacto.** A base de precatórios é inconsistente: há precatório com ente
errado, valor divergente, processo pago sem precatório no tribunal e precatório
sem registro no hub. É o sintoma direto de "os números não batem".

**Causa e consequência.** A causa é a existência de duas fontes independentes
sem conciliação. A consequência é que nenhuma das duas pode ser tratada como
verdade sozinha.

**Tratamento na limpeza.** `saida/relatorio_limpeza.json`, chave
`reconciliacao`, lista `0056789` fora do tribunal e `0067890` ausente no hub. As
divergências de valor e ente não são resolvidas automaticamente.

### 4. Alto — Prazos de pagamento calculados errados

**Evidência.**

- `0012345-10.2019.8.26.0053`: apresentado em 02/04/2025
  (`apresentacoes.json:4`), prazo correto 31/12/2026, mas o hub grava
  31/12/2027 (`hub.csv:2`).
- `0056789-54.2017.4.03.6100`: apresentado em `2025-04-03T01:00:00Z`
  (`apresentacoes.json:20`), que em America/Sao_Paulo é 02/04/2025 22:00; o
  prazo correto é 31/12/2026, mas o hub grava 31/12/2027 (`hub.csv:6`).

**Impacto.** A priorização da carteira fica errada. Um precatório no limite do
prazo pode ser tratado como se tivesse mais um ano.

**Causa e consequência.** A causa é a regra do artigo 100, §1º, da Constituição
não aplicada no hub (ou aplicada sobre a data em UTC, sem converter o fuso). A
consequência é a ordenação incorreta da carteira.

**Tratamento na limpeza.** `src/prazo.py` implementa a regra e o hub é
recalculado; as duas divergências aparecem como "Prazo de pagamento
recalculado" em `saida/relatorio_limpeza.json`. Os demais prazos estavam
corretos (`0023456` em 2027, `0034567` em 2025, `0045678` em 2026).

### 5. Alto — Identificador do processo em formatos diferentes

**Evidência.** `00234562120208260053` aparece em `pagamentos.json:44` (`ev-005`)
e em `hub.csv:3`, sem a máscara CNJ. O mesmo processo é
`0023456-21.2020.8.26.0053` em `tribunal.csv:3`. A documentação exige o formato
CNJ (`DOCUMENTACAO_TRIBUNAL.md:12` e `:24`).

**Impacto.** O pagamento não encontra o precatório; dependendo do script, é
descartado ou cria um precatório duplicado. A comparação manual por string
exata também falha.

**Causa e consequência.** A causa é a ausência de normalização na entrada. A
consequência alimenta o item 3 e a duplicidade de cadastro.

**Tratamento na limpeza.** `normalizar_processo` (`src/norm.py`) converte para o
padrão CNJ e registra "Número CNJ normalizado" no hub.

### 6. Alto — O contrato de dados não corresponde aos arquivos

**Evidência.**

- `DOCUMENTACAO_TRIBUNAL.md:12` diz processo no formato CNJ; `pagamentos.json:44`
  e `hub.csv:3` vêm sem máscara.
- `:13` diz valor numérico; `pagamentos.json:13` traz `"2.500,50"` como texto.
- `:14` diz data `AAAA-MM-DD`; `pagamentos.json:14` traz `"10/04/2025"`.
- `:15` diz tipo sempre `"pagamento"`; `pagamentos.json:63` traz `"estorno"`.
- `:20` diz CSV UTF-8 separado por vírgula; `tribunal.csv` é latin-1 e usa `;`.
- `:26` diz ponto como separador decimal; `tribunal.csv:2` traz `"45.000,00"`.

**Impacto.** Um importador fiel à documentação lê zero registros ou ignora
campos em silêncio. Foi o que aconteceu com a data de apresentação e o nome do
ente: a documentação não cobre `apresentacoes.json` nem `hub.csv`.

**Causa e consequência.** A causa é a documentação v2.1 desatualizada em relação
aos arquivos reais. A consequência é a base vazia ou parcial, que explica os
números errados.

**Tratamento na limpeza.** O leitor aceita os formatos reais (latin-1, `;`,
valor brasileiro, data brasileira, timestamp com fuso) e o relatório registra
"Divergências de documentação" para o delimitador do `tribunal.csv`.

### 7. Médio — Nomes de campo diferentes dos documentados

**Evidência.** `apresentacoes.json:4` usa `apresentado_em`, e `hub.csv:1` usa
`ente` e `apresentado_em`. Nenhum dos dois arquivos está descrito em
`DOCUMENTACAO_TRIBUNAL.md`.

**Impacto.** Um script que procura `data_apresentacao` ou `ente_devedor` não
encontra nada: antes da correção, apresentações e hub tinham 0 importáveis.

**Causa e consequência.** A causa é a falta de leiaute versionado para os
arquivos internos. A consequência é a perda de prazos e de entes, alimentando o
item 4.

**Tratamento na limpeza.** Os dois nomes são aceitos
(`_normalizar_apresentacao` e `_normalizar_csv`), com teste dedicado.

### 8. Médio — O schema não suporta o fluxo

**Evidência.** `schema.sql:3` declara `numero_processo CHAR(20)`, mas o CNJ
formatado tem 25 caracteres. `:11` não tem `UNIQUE` em `evento_id`. `:12` aceita
`estorno`, que a documentação diz não existir. `:13` exige `valor > 0`, o que
impede registrar um estorno negativo. Não há coluna para `atualizado_em`.

**Impacto.** O precatório não pode ser cadastrado com o número documentado: o
PostgreSQL rejeita a inserção com `value too long for type character(20)`; se a
aplicação truncar antes de gravar, perde os últimos dígitos. Duplicatas são
aceitas; o conflito `ev-001` (duas versões) não tem como ser resolvido no banco;
um estorno não pode ser gravado.

**Causa e consequência.** A causa é o schema ter sido desenhado sem observar os
dados. A consequência são os itens 1, 2 e 4.

**Tratamento na limpeza.** O código não grava no banco; o SQL de correção está
na seção de prevenção.

### 9. Médio — Conferência manual no Excel, por string exata

**Evidência.** O operador abre o CSV no Excel, salva e compara ente e processo
"exatamente como estão escritos" (`ENUNCIADO.md:17`).

**Impacto.** A comparação falha por diferença de acento, caixa, máscara ou
espaço; diferenças reais de valor passam despercebidas; o processo não escala e
depende de uma pessoa.

**Causa e consequência.** É consequência da falta de conciliação automatizada e
causa direta de divergências não detectadas (item 3).

### 10. Baixo — Registros inválidos pontuais

**Evidência.** `ev-004` com `valor: null` (`pagamentos.json:37`), `ev-009` com
`-200` (`:85`), `ev-010` com processo vazio (`:92`) e `ev-001` com duas versões
(`:3-9` e `:67-73`).

**Impacto.** Cada um é rejeitado ou gera conflito sem regra definida. Somados,
representam R$ 21.250,00 em pendências.

**Causa e consequência.** A causa é a validação existir só (e de forma
incompleta) no banco, não na origem. A consequência é o item 2.

## Prevenção

### Processo

- Conciliação automática diária entre `tribunal.csv`, `hub.csv` e pagamentos,
  com relatório de divergências e responsável definido.
- Rejeição nunca silenciosa: todo evento não importado entra em fila de
  quarentena com motivo, alerta para a operação e prazo de tratamento.
- Reprocessamento seguro: a importação passa a ser idempotente por `evento_id`
  (e por hash do arquivo), então rodar o mesmo arquivo duas vezes não altera o
  total.
- Leiaute versionado e validado no recebimento (schema, encoding, delimitador,
  formato de valor e data), com aviso ao tribunal quando o arquivo divergir.
- Fim da conferência manual no Excel; a planilha fica só para exceções.
- Trilha de auditoria: arquivo recebido, hash, quem processou, quando e quantos
  registros foram aceitos ou rejeitados.

### Script de importação

- Normalizar o CNJ na entrada e recusar processo que não case com o padrão.
- Converter datas de apresentação para America/Sao_Paulo antes de aplicar a
  regra de prazo.
- Validar antes de gravar: campos obrigatórios, valor, tipo, data e chave;
  falhar o lote em vez de ignorar o registro.
- Gravar em transação por lote, com `UPSERT` por `evento_id`, e registrar os
  rejeitados com o payload original.
- Sair com código de erro e resumo quando houver pendência, para o agendador
  alertar.
- Manter testes para as regras de maior risco: prazo, mapeamento de campos,
  deduplicação e conciliação (já em `tests/`).

### Banco

O SQL está em `migrations/001_prevencao.sql` e deve ser aplicado em uma
transação. Ele:

- muda `numero_processo` para `VARCHAR(25)` e adiciona um CHECK do padrão CNJ
  (criado como `NOT VALID` para não bloquear a migração; validar depois de
  corrigir os dados antigos);
- cria `importacao`, com `hash_arquivo` único, e `pagamento_staging`, que
  recebe as linhas cruas e serve de quarentena;
- remove duplicatas idênticas de `pagamento` e adiciona `UNIQUE (evento_id)`;
- adiciona `atualizado_em` e `importacao_id` ao pagamento;
- corrige os CHECK de tipo e de valor, permitindo estorno negativo;
- cria os índices de conciliação e de importação.

Com isso, a importação passa a ser: registrar o arquivo em `importacao`; gravar
as linhas cruas em `pagamento_staging`; normalizar e mover as válidas para
`pagamento` com `INSERT ... ON CONFLICT (evento_id) DO UPDATE` apenas quando
`atualizado_em` for maior; marcar o resto como `rejeitado` com o motivo. Tudo em
uma transação. Reenviar o mesmo arquivo esbarra no `hash_arquivo` único e não
altera o total.

O `UNIQUE (evento_id)` é o que impede o problema do `ev-002`. Se a resposta à
dúvida 8 for que o id é único apenas dentro do processo, a restrição deve ser
`UNIQUE (precatorio_id, evento_id)`. Duplicatas com conteúdos diferentes, como
o `ev-001`, não são apagadas: o `UNIQUE` falha e obriga a decisão manual. Se a
aplicação já tiver truncado o CNJ antes de gravar, os registros precisam ser
recarregados da fonte, porque o trecho perdido não é recuperável.

## Dúvidas

Perguntas ao tribunal:

1. O `ev-001` aparece com R$ 15.000,00 e R$ 15.500,00; qual versão vale? A regra
   é sempre a de `atualizado_em` mais recente?
2. `estorno` existe? Se sim, como deve ser representado: tipo próprio, valor
   negativo ou valor positivo com sinal indicado em outro campo?
3. `0023456-21.2020.8.26.0053` vale R$ 30.000,00 ou R$ 31.000,00?
4. `0045678-43.2021.5.02.0011` é da União ou do Município de Santos?
5. `0056789-54.2017.4.03.6100` pertence à carteira? Por que só aparece no hub?
6. `0067890-65.2016.8.26.0053` tem pagamento e está no tribunal; por que não está
   no hub?
7. `00234562120208260053` é o mesmo processo de `0023456-21.2020.8.26.0053`?
8. `evento_id` é único globalmente ou só dentro do processo? O mesmo id pode ser
   reenviado com correção?
9. O `pagamentos.json` é incremental de 7 dias ou completo? Como reconciliar
   eventos que saem da janela?
10. A data de apresentação é a do protocolo no tribunal? O prazo considera a
    data local de Brasília? Como tratar 2 de abril caindo em fim de semana?

Perguntas à operação:

11. O que fazer com um evento rejeitado: reprocessar, pedir correção ao tribunal
    ou lançar manualmente? Quem é avisado hoje?
12. Quem é o responsável por conferir as divergências entre tribunal e hub, e
    com que frequência?
13. O valor do hub é o de face ou já atualizado? A diferença de R$ 1.000,00 no
    `0023456` é atualização monetária ou erro?
14. Podemos substituir a conferência no Excel pela conciliação automática, ou
    existe alguma decisão que depende de leitura humana?

## Limitações

A limpeza não decide conflitos de conteúdo (`ev-001`, valor e ente divergentes,
processos ausentes em uma das fontes): ela os expõe como pendência ou
reconciliação. Nenhuma escolha automática foi feita nesses casos justamente
porque depende das respostas acima.
