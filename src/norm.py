
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


FUSO_TRIBUNAL = ZoneInfo("America/Sao_Paulo")


def normalizar_processo(valor: str) -> str | None:
    """
    Padroniza o número CNJ para NNNNNNN-DD.AAAA.J.TR.OOOO.
    Não valida os dígitos verificadores.
    """
    if not valor or not isinstance(valor, str):
        return None

    numeros = re.sub(r"\D", "", valor)

    if len(numeros) != 20:
        return None

    return (
        f"{numeros[:7]}-{numeros[7:9]}."
        f"{numeros[9:13]}.{numeros[13]}."
        f"{numeros[14:16]}.{numeros[16:]}"
    )


def normalizar_nome(valor: str) -> str:
    """
    Normaliza nomes para comparação,
    preservando os valores originais nos arquivos.
    """
    if not valor:
        return ""

    valor = unicodedata.normalize("NFKD", valor)

    valor = "".join(
        caractere
        for caractere in valor
        if not unicodedata.combining(caractere)
    )

    valor = valor.upper().strip()

    return " ".join(valor.split())


def converter_valor(valor) -> Decimal | None:
    """
    Converte valores monetários para Decimal.

    Aceita:
    2500.50
    '2500.50'
    '2.500,50'
    """
    if valor is None or valor == "":
        return None

    try:
        if isinstance(valor, bool):
            return None

        if isinstance(valor, Decimal):
            resultado = valor

        elif isinstance(valor, (int, float)):
            resultado = Decimal(str(valor))

        elif isinstance(valor, str):
            valor = valor.strip()

            if "," in valor:
                valor = valor.replace(".", "")
                valor = valor.replace(",", ".")

            resultado = Decimal(valor)

        else:
            return None

        if not resultado.is_finite():
            return None

        return resultado.quantize(Decimal("0.01"))

    except (InvalidOperation, ValueError):
        return None


def converter_data(valor) -> date | None:
    """
    Interpreta datas ISO, brasileiras e timestamps.
    Timestamps com fuso são convertidos para o
    horário oficial de São Paulo antes da extração da data.
    """
    if not valor:
        return None

    if isinstance(valor, datetime):
        data = valor

    elif isinstance(valor, date):
        return valor

    elif isinstance(valor, str):
        valor = valor.strip()
        try:
            data = datetime.fromisoformat(
                valor.replace("Z", "+00:00")
            )
        except ValueError:
            try:
                return datetime.strptime(
                    valor, "%d/%m/%Y"
                ).date()

            except ValueError:
                return None
    else:
        return None

    if data.tzinfo is not None:
        data = data.astimezone(FUSO_TRIBUNAL)

    return data.date()