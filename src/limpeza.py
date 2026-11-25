import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from src.norm import (
    converter_data,
    converter_valor,
    normalizar_nome,
    normalizar_processo,
)
from src.prazo import calcular_prazo
from src.validacao import classificar_eventos

DIRETORIO_PROJETO = Path(__file__).resolve().parent.parent
DIRETORIO_DADOS = DIRETORIO_PROJETO / "dados"
DIRETORIO_SAIDA = DIRETORIO_PROJETO / "saida"

ARQUIVOS = {
    "pagamentos": DIRETORIO_DADOS / "pagamentos.json",
    "apresentacoes": DIRETORIO_DADOS / "apresentacoes.json",
    "tribunal": DIRETORIO_DADOS / "tribunal.csv",
    "hub": DIRETORIO_DADOS / "hub.csv",
}

# Os formatos documentados e os formatos encontrados
# nos arquivos podem ser diferentes.
DELIMITADORES_DOCUMENTADOS = {
    "tribunal": ",",
    "hub": ",",
}

ARQUIVOS_JSON = {"pagamentos", "apresentacoes"}

CATEGORIAS = (
    "importaveis",
    "corrigidos",
    "descartados",
    "pendentes",
    "aprovados_sem_alteracao",
)


def _converter_saida(valor):
    """Converte Decimal e datas para texto na hora de gravar."""
    if isinstance(valor, Decimal):
        return str(valor)

    if isinstance(valor, (date, datetime)):
        return valor.isoformat()

    return valor


def serializar_json(valor):
    """Converte tipos não nativos em texto para serialização em JSON."""
    if isinstance(valor, (date, datetime, Decimal)):
        return _converter_saida(valor)

    raise TypeError(
        f"Tipo não serializável: {type(valor).__name__}"
    )


def salvar_json(caminho, conteudo):
    """Grava um conteúdo JSON em UTF-8, criando o diretório de destino."""
    caminho.parent.mkdir(parents=True, exist_ok=True)

    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(
            conteudo,
            arquivo,
            ensure_ascii=False,
            indent=4,
            default=serializar_json,
        )


def salvar_csv(caminho, registros):
    """Grava registros em CSV com vírgula, convertendo datas e decimais."""
    caminho.parent.mkdir(parents=True, exist_ok=True)

    if not registros:
        caminho.write_text("", encoding="utf-8")
        return

    colunas = list(registros[0].keys())

    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=colunas,
            delimiter=",",
            extrasaction="ignore",
        )
        escritor.writeheader()

        for registro in registros:
            escritor.writerow({
                coluna: _converter_saida(registro.get(coluna))
                for coluna in colunas
            })


def carregar_json(caminho):
    """Lê um arquivo JSON em UTF-8, ignorando eventual BOM."""
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}"
        )

    with caminho.open("r", encoding="utf-8-sig") as arquivo:
        return json.load(arquivo)


def carregar_csv(caminho):
    """Lê um CSV detectando a codificação e o delimitador.

    Tenta UTF-8 (ignorando BOM) e recorre a latin-1 em caso de falha. Retorna
    os registros e o delimitador detectado, que pode divergir da documentação.
    """
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}"
        )

    bruto = caminho.read_bytes()

    try:
        conteudo = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        conteudo = bruto.decode("latin-1")

    try:
        delimitador = csv.Sniffer().sniff(
            conteudo[:4096],
            delimiters=",;"
        ).delimiter
    except csv.Error:
        delimitador = ","

    leitor = csv.DictReader(
        conteudo.splitlines(),
        delimiter=delimitador
    )

    return list(leitor), delimitador


def preparar_resultado():
    """Cria a estrutura vazia de classificação de uma fonte de dados."""
    return {categoria: [] for categoria in CATEGORIAS}


def registrar_pendente(resultado, indice, registro, motivos):
    """Registra um registro que não pôde ser importado, com os motivos."""
    resultado["pendentes"].append({
        "indice": indice,
        "registro": registro,
        "motivos": motivos,
    })


def obter_campo(registro, alternativas):
    """Procura um campo aceitando nomes alternativos."""
    for nome in alternativas:
        if nome in registro:
            return nome, registro[nome]

    return None, None


def resumir_resultado(resultado):
    """Conta quantos registros caíram em cada categoria."""
    return {
        categoria: len(resultado[categoria])
        for categoria in CATEGORIAS
    }


def _processar_chave(
    processos,
    resultado,
    chave,
    indice,
    registro,
    normalizado,
    ajustes,
    motivo_duplicata,
    motivo_conflito,
):
    """Guarda o primeiro registro de cada chave e resolve repetições.

    Registros idênticos viram descarte; registros divergentes para a mesma
    chave marcam conflito e vão para pendentes, junto com o primeiro registro.
    """
    anterior = processos.get(chave)

    if anterior is None:
        processos[chave] = {
            "indice": indice,
            "original": registro,
            "normalizado": normalizado,
            "conflito": False,
            "ajustes": ajustes,
        }
        return

    if anterior["normalizado"] == normalizado:
        resultado["descartados"].append({
            "indice": indice,
            "registro": registro,
            "motivo": motivo_duplicata,
        })
        return

    anterior["conflito"] = True

    registrar_pendente(
        resultado,
        anterior["indice"],
        anterior["original"],
        [motivo_conflito],
    )
    registrar_pendente(
        resultado,
        indice,
        registro,
        [motivo_conflito],
    )


def _finalizar(processos, resultado):
    """Distribui os registros aceitos entre importáveis e as demais listas."""
    for item in processos.values():
        if item["conflito"]:
            continue

        resultado["importaveis"].append(item["normalizado"])

        if item["ajustes"]:
            resultado["corrigidos"].append({
                "indice": item["indice"],
                "original": item["original"],
                "normalizado": item["normalizado"],
                "ajustes": item["ajustes"],
            })
        else:
            resultado["aprovados_sem_alteracao"].append({
                "indice": item["indice"],
            })

    return resultado


def _classificar(registros, normalizar, motivo_duplicata, motivo_conflito):
    """Aplica a normalização de cada registro e resolve duplicatas por processo.

    `normalizar` deve devolver (processo, normalizado, motivos, ajustes).
    """
    resultado = preparar_resultado()
    processos = {}

    for indice, registro in enumerate(registros):
        if not isinstance(registro, dict):
            registrar_pendente(
                resultado,
                indice,
                registro,
                ["Registro não é um objeto JSON."],
            )
            continue

        processo, normalizado, motivos, ajustes = normalizar(registro)

        if motivos:
            registrar_pendente(resultado, indice, registro, motivos)
            continue

        _processar_chave(
            processos,
            resultado,
            processo,
            indice,
            registro,
            normalizado,
            ajustes,
            motivo_duplicata,
            motivo_conflito,
        )

    return _finalizar(processos, resultado)


def _normalizar_apresentacao(registro):
    """Normaliza processo e data de um registro de apresentação."""
    motivos = []
    ajustes = []

    campo_processo, processo_original = obter_campo(
        registro,
        ["processo", "numero_processo"],
    )
    campo_data, data_original = obter_campo(
        registro,
        ["apresentado_em", "data_apresentacao", "data_apresentação"],
    )

    processo = normalizar_processo(processo_original)
    data_apresentacao = converter_data(data_original)

    if processo is None:
        motivos.append("Número do processo inválido.")
    elif processo_original != processo:
        ajustes.append("Número CNJ normalizado.")

    if data_apresentacao is None:
        motivos.append("Data de apresentação inválida.")
    elif str(data_original) != data_apresentacao.isoformat():
        ajustes.append("Data de apresentação normalizada.")

    normalizado = dict(registro)
    normalizado[campo_processo] = processo
    normalizado[campo_data] = data_apresentacao

    return processo, normalizado, motivos, ajustes


def _normalizar_csv(registro, origem):
    """Normaliza processo, ente, valor e (no hub) as datas de um registro CSV."""
    motivos = []
    ajustes = []

    campo_processo, processo_original = obter_campo(
        registro,
        ["numero_processo", "processo"],
    )
    campo_ente, ente_original = obter_campo(
        registro,
        ["ente_devedor", "ente"],
    )
    campo_valor, valor_original = obter_campo(
        registro,
        ["valor_face", "valor"],
    )

    if campo_processo is None:
        motivos.append("Coluna de número do processo ausente.")

    if campo_ente is None:
        motivos.append("Coluna ente_devedor ausente.")

    if campo_valor is None:
        motivos.append("Coluna de valor ausente.")

    processo = normalizar_processo(processo_original)
    ente = normalizar_nome(ente_original)
    valor = converter_valor(valor_original)

    if campo_processo and processo is None:
        motivos.append("Número do processo inválido.")
    elif processo is not None and processo != processo_original:
        ajustes.append("Número CNJ normalizado.")

    if campo_ente and not ente:
        motivos.append("Ente devedor ausente ou inválido.")
    elif campo_ente and ente != ente_original:
        ajustes.append("Nome do ente devedor normalizado.")

    if campo_valor and valor is None:
        motivos.append("Valor ausente ou inválido.")
    elif valor is not None and valor < 0:
        motivos.append("Valor negativo.")
    elif valor is not None and valor != valor_original:
        ajustes.append("Valor monetário normalizado.")

    normalizado = dict(registro)

    if campo_processo and processo is not None:
        normalizado[campo_processo] = processo

    if campo_ente and ente:
        normalizado[campo_ente] = ente

    if campo_valor and valor is not None:
        normalizado[campo_valor] = valor

    if origem == "hub":
        _normalizar_hub(registro, normalizado, motivos, ajustes)

    return processo, normalizado, motivos, ajustes


def _normalizar_hub(registro, normalizado, motivos, ajustes):
    """Normaliza as datas e recalcula o prazo constitucional do hub."""
    campo_data, data_original = obter_campo(
        registro,
        ["apresentado_em", "data_apresentacao", "data_apresentação"],
    )
    campo_prazo, prazo_original = obter_campo(
        registro,
        ["prazo_pagamento", "data_prazo"],
    )

    apresentado_em = None

    if campo_data is not None:
        apresentado_em = converter_data(data_original)

        if apresentado_em is None:
            motivos.append(f"Data inválida na coluna {campo_data}.")
        else:
            normalizado[campo_data] = apresentado_em

            if str(data_original) != apresentado_em.isoformat():
                ajustes.append(f"Data da coluna {campo_data} normalizada.")

    if apresentado_em is not None:
        esperado = calcular_prazo(apresentado_em)
        prazo_atual = converter_data(normalizado.get("prazo_pagamento"))

        normalizado["prazo_pagamento"] = esperado

        if prazo_atual != esperado:
            ajustes.append(
                "Prazo de pagamento recalculado pela regra constitucional."
            )

        return

    if campo_prazo is not None:
        prazo = converter_data(prazo_original)

        if prazo is None:
            motivos.append(f"Data inválida na coluna {campo_prazo}.")
        else:
            normalizado[campo_prazo] = prazo

            if str(prazo_original) != prazo.isoformat():
                ajustes.append(f"Data da coluna {campo_prazo} normalizada.")


def limpar_apresentacoes(registros):
    """Normaliza as datas de apresentação e resolve duplicatas por processo."""
    if not isinstance(registros, list):
        raise ValueError(
            "apresentacoes.json deve conter uma lista."
        )

    return _classificar(
        registros,
        _normalizar_apresentacao,
        "Duplicata idêntica de apresentação.",
        "Processo possui apresentações divergentes.",
    )


def limpar_csv(registros, origem):
    """Normaliza processo, ente e valor, e trata duplicatas de tribunal/hub."""
    return _classificar(
        registros,
        lambda registro: _normalizar_csv(registro, origem),
        "Registro duplicado idêntico.",
        "Processo possui registros divergentes na mesma fonte.",
    )


def limpar_pagamentos(registros):
    """Delega a validação e a classificação dos eventos de pagamento."""
    return classificar_eventos(registros)


def _processos(resultado):
    """Extrai os números de processo já normalizados de uma fonte."""
    return {
        registro.get("numero_processo") or registro.get("processo")
        for registro in resultado["importaveis"]
    }


def reconciliar_processos(resultados):
    """Compara os processos importados de cada fonte com a lista do tribunal."""
    por_fonte = {
        nome: _processos(resultado)
        for nome, resultado in resultados.items()
    }
    tribunal = por_fonte.get("tribunal", set())

    return {
        "fora_do_tribunal": {
            nome: sorted(processos - tribunal)
            for nome, processos in por_fonte.items()
            if nome != "tribunal" and processos - tribunal
        },
        "tribunal_ausente_em": {
            nome: sorted(tribunal - processos)
            for nome, processos in por_fonte.items()
            if nome != "tribunal" and tribunal - processos
        },
    }


def montar_relatorio(resultados, divergencias):
    """Consolida resumo, ajustes, pendências e reconciliação das fontes."""
    relatorio = {
        "arquivos_processados": [
            caminho.name for caminho in ARQUIVOS.values()
        ],
        "resumo": {
            nome: resumir_resultado(resultado)
            for nome, resultado in resultados.items()
        },
    }

    for categoria in ("corrigidos", "descartados", "pendentes",
                      "aprovados_sem_alteracao"):
        relatorio[categoria] = {
            nome: resultado[categoria]
            for nome, resultado in resultados.items()
        }

    relatorio["reconciliacao"] = reconciliar_processos(resultados)
    relatorio["divergencias_documentacao"] = divergencias

    return relatorio


def gravar_saidas(resultados, relatorio):
    """Grava a base limpa de cada fonte e os arquivos de relatório."""
    DIRETORIO_SAIDA.mkdir(parents=True, exist_ok=True)

    for nome, resultado in resultados.items():
        if nome in ARQUIVOS_JSON:
            caminho = DIRETORIO_SAIDA / f"{nome}_limpos.json"
            salvar_json(caminho, resultado["importaveis"])
        else:
            caminho = DIRETORIO_SAIDA / f"{nome}_limpos.csv"
            salvar_csv(caminho, resultado["importaveis"])

    artefatos = {
        "relatorio_limpeza.json": relatorio,
        "registros_descartados.json": relatorio["descartados"],
        "registros_pendentes.json": relatorio["pendentes"],
    }

    for nome, conteudo in artefatos.items():
        salvar_json(DIRETORIO_SAIDA / nome, conteudo)


def imprimir_resumo(resultados, divergencias):
    """Mostra no terminal o resumo da limpeza e os arquivos gerados."""
    print("\nRESUMO DO PROCESSAMENTO")
    print("-" * 60)

    for nome, resultado in resultados.items():
        print(f"\nArquivo: {nome}")

        for categoria, quantidade in resumir_resultado(resultado).items():
            print(f"  {categoria}: {quantidade}")

    print("\nDivergências de documentação:")
    for divergencia in divergencias:
        print(
            f"  {divergencia['arquivo']}: "
            f"{divergencia['problema']}"
        )

    print("\nArquivos gerados:")
    for arquivo in sorted(DIRETORIO_SAIDA.iterdir()):
        if arquivo.is_file():
            print(f"  {arquivo.name}")


def executar_limpeza():
    """Executa a limpeza das quatro fontes e grava base e relatório na saída."""
    print("=" * 60)
    print("INICIANDO LIMPEZA DOS ARQUIVOS")
    print("=" * 60)

    resultados = {
        "pagamentos": limpar_pagamentos(
            carregar_json(ARQUIVOS["pagamentos"])
        ),
        "apresentacoes": limpar_apresentacoes(
            carregar_json(ARQUIVOS["apresentacoes"])
        ),
    }
    divergencias = []

    for origem in ("tribunal", "hub"):
        registros, delimitador = carregar_csv(ARQUIVOS[origem])
        resultados[origem] = limpar_csv(registros, origem)

        documentado = DELIMITADORES_DOCUMENTADOS[origem]

        if delimitador != documentado:
            divergencias.append({
                "arquivo": ARQUIVOS[origem].name,
                "problema": "Delimitador diferente do documentado.",
                "delimitador_documentado": documentado,
                "delimitador_encontrado": delimitador,
            })

    relatorio = montar_relatorio(resultados, divergencias)

    gravar_saidas(resultados, relatorio)
    imprimir_resumo(resultados, divergencias)

    print("\nLIMPEZA FINALIZADA")
