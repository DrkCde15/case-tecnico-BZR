from datetime import date, datetime
from decimal import Decimal
import pytest
from src.norm import (
    converter_data,
    converter_valor,
    normalizar_nome,
    normalizar_processo,
)

class TestNormalizarProcesso:
    def test_mantem_numero_ja_formatado(self):
        assert (
            normalizar_processo("0012345-10.2019.8.26.0053")
            == "0012345-10.2019.8.26.0053"
        )

    def test_formata_numero_sem_separadores(self):
        assert (
            normalizar_processo("00234562120208260053")
            == "0023456-21.2020.8.26.0053"
        )

    def test_ignora_caracteres_nao_numericos(self):
        assert (
            normalizar_processo(" 0023456 21 2020 8 26 0053 ")
            == "0023456-21.2020.8.26.0053"
        )

    @pytest.mark.parametrize("valor", ["", "123", "0" * 21, None, 12345678901234567890])
    def test_retorna_none_para_entrada_invalida(self, valor):
        assert normalizar_processo(valor) is None


class TestNormalizarNome:
    def test_remove_acentos_e_converte_caixa(self):
        assert normalizar_nome("Município de São Paulo") == "MUNICIPIO DE SAO PAULO"

    def test_colapsa_espacos(self):
        assert normalizar_nome("  Estado   de   São Paulo ") == "ESTADO DE SAO PAULO"

    @pytest.mark.parametrize("valor", ["", None])
    def test_entrada_vazia_retorna_string_vazia(self, valor):
        assert normalizar_nome(valor) == ""


class TestConverterValor:
    @pytest.mark.parametrize(
        "valor, esperado",
        [
            (15000.0, Decimal("15000.00")),
            (8000, Decimal("8000.00")),
            ("2500.50", Decimal("2500.50")),
            ("2.500,50", Decimal("2500.50")),
            ("0,01", Decimal("0.01")),
            (Decimal("42.5"), Decimal("42.50")),
        ],
    )
    def test_converte_formatos_aceitos(self, valor, esperado):
        assert converter_valor(valor) == esperado

    def test_arredonda_para_duas_casas(self):
        assert converter_valor("10.005") == Decimal("10.00")

    @pytest.mark.parametrize(
        "valor",
        [None, "", "abc", "R$ 10,00", True, False, float("nan"), float("inf"), [], {}],
    )
    def test_retorna_none_quando_nao_converte(self, valor):
        assert converter_valor(valor) is None


class TestConverterData:
    def test_data_iso(self):
        assert converter_data("2025-04-02") == date(2025, 4, 2)

    def test_data_brasileira(self):
        assert converter_data("10/04/2025") == date(2025, 4, 10)

    def test_preserva_objeto_date(self):
        assert converter_data(date(2024, 2, 29)) == date(2024, 2, 29)

    def test_timestamp_com_fuso_de_sao_paulo(self):
        assert converter_data("2025-04-02T23:30:00-03:00") == date(2025, 4, 2)

    def test_timestamp_utc_convertido_para_sao_paulo(self):
        # 2025-04-03T01:00:00Z -> 2025-04-02 22:00 em São Paulo
        assert converter_data("2025-04-03T01:00:00Z") == date(2025, 4, 2)

    def test_datetime_sem_fuso(self):
        assert converter_data(datetime(2025, 5, 2, 11, 0)) == date(2025, 5, 2)

    @pytest.mark.parametrize(
        "valor", [None, "", "2025-13-01", "31/02/2024", "ontem", 20250402]
    )
    def test_retorna_none_quando_nao_converte(self, valor):
        assert converter_data(valor) is None
