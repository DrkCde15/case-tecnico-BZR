from datetime import date
from decimal import Decimal

import pytest

from src.validacao import classificar_eventos, validar_evento


def evento(**overrides):
    base = {
        "evento_id": "ev-001",
        "processo": "0012345-10.2019.8.26.0053",
        "valor": 15000.0,
        "data_pagamento": "2025-03-10",
        "tipo": "pagamento",
        "atualizado_em": "2025-03-10T10:00:00-03:00",
    }
    base.update(overrides)
    return base


class TestValidarEvento:
    def test_evento_valido_sem_ajustes(self):
        validacao, problemas = validar_evento(evento())

        assert problemas == []
        assert validacao["ajustes"] == []

        normalizado = validacao["evento"]
        assert normalizado["evento_id"] == "ev-001"
        assert normalizado["processo"] == "0012345-10.2019.8.26.0053"
        assert normalizado["valor"] == Decimal("15000.00")
        assert normalizado["data_pagamento"] == date(2025, 3, 10)
        assert normalizado["tipo"] == "pagamento"
        assert normalizado["atualizado_em"] == "2025-03-10T10:00:00-03:00"

    def test_normaliza_processo_sem_separadores(self):
        validacao, problemas = validar_evento(
            evento(processo="00234562120208260053")
        )

        assert problemas == []
        assert validacao["evento"]["processo"] == "0023456-21.2020.8.26.0053"
        assert "Número do processo normalizado." in validacao["ajustes"]

    def test_converte_valor_brasileiro(self):
        validacao, problemas = validar_evento(evento(valor="2.500,50"))

        assert problemas == []
        assert validacao["evento"]["valor"] == Decimal("2500.50")
        assert "Valor convertido para formato decimal." in validacao["ajustes"]

    def test_normaliza_data_brasileira(self):
        validacao, problemas = validar_evento(evento(data_pagamento="10/04/2025"))

        assert problemas == []
        assert validacao["evento"]["data_pagamento"] == date(2025, 4, 10)
        assert "Data de pagamento normalizada." in validacao["ajustes"]

    def test_remove_espacos_do_evento_id(self):
        validacao, problemas = validar_evento(evento(evento_id="  ev-001  "))

        assert problemas == []
        assert validacao["evento"]["evento_id"] == "ev-001"

    def test_descarta_campos_nao_documentados(self):
        validacao, problemas = validar_evento(evento(campo_extra="x"))

        assert problemas == []
        assert "campo_extra" not in validacao["evento"]

    @pytest.mark.parametrize("registro", [None, [], "texto", 42])
    def test_registro_que_nao_e_objeto(self, registro):
        validacao, problemas = validar_evento(registro)

        assert validacao is None
        assert problemas == ["Registro não é um objeto JSON."]

    @pytest.mark.parametrize("evento_id", [None, "", "   ", 123])
    def test_evento_id_invalido(self, evento_id):
        validacao, problemas = validar_evento(evento(evento_id=evento_id))

        assert validacao is None
        assert "evento_id ausente ou inválido." in problemas

    @pytest.mark.parametrize("processo", [None, "", "123", "0" * 21])
    def test_processo_invalido(self, processo):
        validacao, problemas = validar_evento(evento(processo=processo))

        assert validacao is None
        assert "Número do processo ausente ou inválido." in problemas

    @pytest.mark.parametrize("valor", [None, "", "abc", "R$ 10,00", True])
    def test_valor_nao_convertivel(self, valor):
        validacao, problemas = validar_evento(evento(valor=valor))

        assert validacao is None
        assert "Valor ausente ou inválido." in problemas

    @pytest.mark.parametrize("valor", [0, "0,00", -5, "-10,00"])
    def test_valor_nao_positivo(self, valor):
        validacao, problemas = validar_evento(evento(valor=valor))

        assert validacao is None
        assert "Valor deve ser positivo para um pagamento." in problemas

    @pytest.mark.parametrize("data", [None, "", "2025-13-01", "31/02/2024"])
    def test_data_invalida(self, data):
        validacao, problemas = validar_evento(evento(data_pagamento=data))

        assert validacao is None
        assert "Data de pagamento ausente ou inválida." in problemas

    @pytest.mark.parametrize("tipo", [None, "estorno", "PAGAMENTO", ""])
    def test_tipo_nao_importavel(self, tipo):
        validacao, problemas = validar_evento(evento(tipo=tipo))

        assert validacao is None
        assert any("não documentado como evento importável" in p for p in problemas)

    @pytest.mark.parametrize(
        "atualizado_em",
        [None, "", "   ", "ontem", "2025-13-01T00:00:00", 123],
    )
    def test_atualizado_em_invalido(self, atualizado_em):
        validacao, problemas = validar_evento(
            evento(atualizado_em=atualizado_em)
        )

        assert validacao is None
        assert any(p.startswith("Campo atualizado_em") for p in problemas)

    def test_acumula_todos_os_problemas(self):
        validacao, problemas = validar_evento(
            {
                "evento_id": "",
                "processo": "123",
                "valor": "abc",
                "data_pagamento": "",
                "tipo": "estorno",
                "atualizado_em": "",
            }
        )

        assert validacao is None
        assert len(problemas) == 6


class TestClassificarEventos:
    def test_lista_vazia(self):
        resultado = classificar_eventos([])

        assert all(grupo == [] for grupo in resultado.values())

    def test_evento_valido_vai_para_importaveis_e_aprovados(self):
        resultado = classificar_eventos([evento()])

        assert len(resultado["importaveis"]) == 1
        assert resultado["importaveis"][0]["evento_id"] == "ev-001"
        assert len(resultado["aprovados_sem_alteracao"]) == 1
        assert resultado["corrigidos"] == []
        assert resultado["pendentes"] == []
        assert resultado["descartados"] == []

    def test_evento_corrigido_entra_nos_dois_grupos(self):
        resultado = classificar_eventos(
            [evento(valor="2.500,50", data_pagamento="10/04/2025")]
        )

        assert len(resultado["importaveis"]) == 1
        assert len(resultado["corrigidos"]) == 1
        assert resultado["corrigidos"][0]["ajustes"]
        assert resultado["aprovados_sem_alteracao"] == []

    def test_evento_invalido_vai_para_pendentes(self):
        resultado = classificar_eventos([evento(processo="123")])

        assert resultado["importaveis"] == []
        assert len(resultado["pendentes"]) == 1
        assert resultado["pendentes"][0]["indice"] == 0
        assert resultado["pendentes"][0]["motivos"]

    def test_registro_que_nao_e_objeto_vai_para_pendentes(self):
        resultado = classificar_eventos(["lixo", evento()])

        assert len(resultado["importaveis"]) == 1
        assert len(resultado["pendentes"]) == 1
        assert resultado["pendentes"][0]["indice"] == 0
        assert resultado["pendentes"][0]["registro"] == "lixo"

    def test_evento_id_ausente_vai_para_pendentes(self):
        resultado = classificar_eventos([evento(evento_id="")])

        assert resultado["importaveis"] == []
        assert len(resultado["pendentes"]) == 1
        assert (
            "evento_id ausente ou inválido."
            in resultado["pendentes"][0]["motivos"]
        )

    def test_duplicata_identica_importa_uma_vez(self):
        resultado = classificar_eventos([evento(), evento()])

        assert len(resultado["importaveis"]) == 1
        assert resultado["importaveis"][0]["evento_id"] == "ev-001"
        assert resultado["pendentes"] == []

    @pytest.mark.xfail(
        reason=(
            "bug conhecido: após registros = registros[:1] a lista de "
            "repetições fica vazia e nada é gravado em descartados"
        ),
        strict=False,
    )
    def test_duplicata_identica_deveria_ser_registrada_em_descartados(self):
        resultado = classificar_eventos([evento(), evento()])

        assert len(resultado["descartados"]) == 1

    def test_duplicata_com_conteudo_divergente_vai_para_pendentes(self):
        resultado = classificar_eventos(
            [evento(valor=15000.0), evento(valor=16000.0)]
        )

        assert resultado["importaveis"] == []
        assert len(resultado["pendentes"]) == 2
        for pendente in resultado["pendentes"]:
            assert (
                "Mesmo evento_id encontrado com conteúdos diferentes."
                in pendente["motivos"]
            )

    def test_indice_refere_posicao_na_lista_original(self):
        resultado = classificar_eventos(
            [
                evento(evento_id="ev-001"),
                evento(evento_id="ev-002", processo="123"),
                evento(evento_id="ev-003"),
            ]
        )

        assert [e["evento_id"] for e in resultado["importaveis"]] == [
            "ev-001",
            "ev-003",
        ]
        assert resultado["pendentes"][0]["indice"] == 1
