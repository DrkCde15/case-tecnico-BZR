import csv
import json
import pandas as pd

def load_json(file):
    """
    Carrega um arquivo JSON ignorando um eventual BOM UTF-8.

    Args:
        file: Caminho do arquivo JSON a ser lido.

    Returns:
        O conteúdo do arquivo já desserializado pelo módulo ``json``.
    """
    with file.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_csv(file):
    """
    Lê um CSV tolerante a diferenças de codificação e delimitador.

    Tenta decodificar como UTF-8 (ignorando BOM) e recorre a ``latin-1`` em caso
    de falha. O delimitador é detectado com ``csv.Sniffer`` e, se a detecção
    falhar, escolhe-se entre vírgula e ponto e vírgula pela maior ocorrência.
    Cabeçalhos e valores são normalizados com ``strip``.

    Args:
        file: Caminho do arquivo CSV a ser lido.

    Returns:
        Um ``pandas.DataFrame`` com a lista de linhas, expondo o delimitador e a
        codificação detectados em ``df.attrs``.
    """
    raw = file.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
        encoding = "utf-8"
    except UnicodeDecodeError:
        content = raw.decode("latin-1")
        encoding = "latin-1"

    try:
        delimiter = csv.Sniffer().sniff(
            content[:2048], delimiters=",;"
        ).delimiter
    except csv.Error:
        delimiter = ";" if content.count(";") > content.count(",") else ","

    reader = csv.DictReader(content.splitlines(), delimiter=delimiter)
    rows = [
        {str(k).strip(): (v or "").strip() for k, v in row.items()}
        for row in reader
    ]
    df = pd.DataFrame(rows)
    df.attrs["delimiter"] = delimiter
    df.attrs["encoding"] = encoding
    return df