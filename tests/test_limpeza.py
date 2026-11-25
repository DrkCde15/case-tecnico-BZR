import json
from datetime import date
from decimal import Decimal
import pytest
from src import limpeza

PROCESSO = "0012345-10.2019.8.26.0053"
OUTRO_PROCESSO = "0023456-21.2020.8.26.0053"


def apresentacao(**overrides):
    base = {"processo": PROCESSO, "apresentado_em": "2025-04-02"}
    base.update(overrides)
    return base


def linha_tribunal(**overrides):
    base = {
        "numero_processo": PROCESSO,
        "ente_devedor": "Município de São Paulo",
        "valor_face": "45.000,00",
    }
    base.update(overrides)
    return base


def linha_hub(**overrides):
    base = {
        "processo": PROCESSO,
        "ente": "Município de São Paulo",
        "valor_face": "45.000,00",
        "apresentado_em": "2025-04-02",
        "prazo_pagamento": "2027-12-31",
    }
    base.update(overrides)
    return base


def resultado_com(importaveis):
    resultado = limpeza.preparar_resultado()
    resultado["importaveis"] = list(importaveis)
    return resultado


class TestLimparApresentacoes:
    def test_le_campo_apresentado_em(self):
        resultado = limpeza.limpar_apresentacoes([apresentacao()])

        assert len(resultado["importaveis"]) == 1
        assert resultado["importaveis"][0]["apresentado_em"] == date(2025, 4, 2)
        assert len(resultado["aprovados_sem_alteracao"]) == 1
        assert resultado["pendentes"] == []

    def test_aceita_nome_alternativo_de_data(self):
        registro = {"processo": PROCESSO, "data_apresentacao": "2025-04-02"}

        resultado = limpeza.limpar_apresentacoes([registro])

        assert len(resultado["importaveis"]) == 1
        assert resultado["importaveis"][0]["data_apresentacao"] == date(2025, 4, 2)

    def test_duplicata_identica_e_descartada(self):
        resultado = limpeza.limpar_apresentacoes([apresentacao(), apresentacao()])

        assert len(resultado["importaveis"]) == 1
        assert len(resultado["descartados"]) == 1
        assert resultado["descartados"][0]["indice"] == 1

    def test_apresentacoes_divergentes_vao_para_pendentes(self):
        resultado = limpeza.limpar_apresentacoes([
            apresentacao(apresentado_em="2024-01-01"),
            apresentacao(apresentado_em="2025-01-01"),
        ])

        assert resultado["importaveis"] == []
        assert len(resultado["pendentes"]) == 2

    def test_data_invalida_vai_para_pendentes(self):
        resultado = limpeza.limpar_apresentacoes([
            apresentacao(apresentado_em="31/02/2025"),
        ])

        assert resultado["importaveis"] == []
        assert "Data de apresentação inválida." in resultado["pendentes"][0]["motivos"]

    def test_registro_que_nao_e_objeto(self):
        resultado = limpeza.limpar_apresentacoes(["lixo"])

        assert resultado["pendentes"][0]["registro"] == "lixo"

    def test_entrada_que_nao_e_lista(self):
        with pytest.raises(ValueError):
            limpeza.limpar_apresentacoes({"processo": PROCESSO})


class TestLimparTribunal:
    def test_normaliza_processo_ente_e_valor(self):
        resultado = limpeza.limpar_csv([linha_tribunal()], "tribunal")

        assert len(resultado["importaveis"]) == 1
        item = resultado["importaveis"][0]
        assert item["numero_processo"] == PROCESSO
        assert item["ente_devedor"] == "MUNICIPIO DE SAO PAULO"
        assert item["valor_face"] == Decimal("45000.00")
        assert resultado["corrigidos"][0]["ajustes"]

    def test_coluna_ente_ausente(self):
        registro = linha_tribunal()
        del registro["ente_devedor"]

        resultado = limpeza.limpar_csv([registro], "tribunal")

        assert resultado["importaveis"] == []
        assert "Coluna ente_devedor ausente." in resultado["pendentes"][0]["motivos"]

    def test_valor_negativo(self):
        resultado = limpeza.limpar_csv(
            [linha_tribunal(valor_face="-10,00")],
            "tribunal",
        )

        assert "Valor negativo." in resultado["pendentes"][0]["motivos"]

    def test_duplicata_identica_e_descartada(self):
        resultado = limpeza.limpar_csv(
            [linha_tribunal(), linha_tribunal()],
            "tribunal",
        )

        assert len(resultado["importaveis"]) == 1
        assert len(resultado["descartados"]) == 1


class TestLimparHub:
    def test_aceita_coluna_ente(self):
        resultado = limpeza.limpar_csv([linha_hub()], "hub")

        assert len(resultado["importaveis"]) == 1
        assert resultado["importaveis"][0]["ente"] == "MUNICIPIO DE SAO PAULO"

    def test_recalcula_prazo_divergente(self):
        resultado = limpeza.limpar_csv([linha_hub()], "hub")

        item = resultado["importaveis"][0]
        assert item["apresentado_em"] == date(2025, 4, 2)
        assert item["prazo_pagamento"] == date(2026, 12, 31)
        assert any(
            "Prazo de pagamento recalculado" in ajuste
            for ajuste in resultado["corrigidos"][0]["ajustes"]
        )

    def test_prazo_correto_nao_gera_ajuste_de_prazo(self):
        resultado = limpeza.limpar_csv(
            [linha_hub(apresentado_em="2025-04-03", prazo_pagamento="2027-12-31")],
            "hub",
        )

        ajustes = resultado["corrigidos"][0]["ajustes"]
        assert not any("Prazo de pagamento" in ajuste for ajuste in ajustes)
        assert resultado["importaveis"][0]["prazo_pagamento"] == date(2027, 12, 31)

    def test_calcula_prazo_quando_coluna_ausente(self):
        registro = linha_hub()
        del registro["prazo_pagamento"]

        resultado = limpeza.limpar_csv([registro], "hub")

        assert (
            resultado["importaveis"][0]["prazo_pagamento"]
            == date(2026, 12, 31)
        )

    def test_data_de_apresentacao_invalida(self):
        resultado = limpeza.limpar_csv(
            [linha_hub(apresentado_em="ontem")],
            "hub",
        )

        assert resultado["importaveis"] == []
        assert (
            "Data inválida na coluna apresentado_em."
            in resultado["pendentes"][0]["motivos"]
        )


class TestRelatorio:
    def test_resumir_resultado(self):
        resultado = limpeza.preparar_resultado()
        resultado["importaveis"] = [1, 2]
        resultado["pendentes"] = [1]

        assert limpeza.resumir_resultado(resultado) == {
            "importaveis": 2,
            "corrigidos": 0,
            "descartados": 0,
            "pendentes": 1,
            "aprovados_sem_alteracao": 0,
        }

    def test_reconciliar_processos(self):
        resultados = {
            "tribunal": resultado_com([{"numero_processo": PROCESSO}]),
            "hub": resultado_com([
                {"processo": PROCESSO},
                {"processo": OUTRO_PROCESSO},
            ]),
        }

        reconciliacao = limpeza.reconciliar_processos(resultados)

        assert reconciliacao["fora_do_tribunal"] == {
            "hub": [OUTRO_PROCESSO],
        }
        assert reconciliacao["tribunal_ausente_em"] == {}

    def test_reconciliar_processo_do_tribunal_ausente(self):
        resultados = {
            "tribunal": resultado_com([{"numero_processo": PROCESSO}]),
            "hub": resultado_com([{"processo": OUTRO_PROCESSO}]),
        }

        reconciliacao = limpeza.reconciliar_processos(resultados)

        assert reconciliacao["tribunal_ausente_em"] == {"hub": [PROCESSO]}

    def test_montar_relatorio_inclui_reconciliacao(self):
        resultados = {
            "tribunal": resultado_com([{"numero_processo": PROCESSO}]),
            "hub": resultado_com([{"processo": PROCESSO}]),
        }

        relatorio = limpeza.montar_relatorio(resultados, [])

        assert relatorio["resumo"]["tribunal"]["importaveis"] == 1
        assert relatorio["reconciliacao"] == {
            "fora_do_tribunal": {},
            "tribunal_ausente_em": {},
        }
        assert relatorio["divergencias_documentacao"] == []


class TestSerializacao:
    def test_serializar_decimal_e_data(self):
        assert limpeza.serializar_json(Decimal("10.50")) == "10.50"
        assert limpeza.serializar_json(date(2025, 4, 2)) == "2025-04-02"

    def test_serializar_tipo_invalido(self):
        with pytest.raises(TypeError):
            limpeza.serializar_json(object())

    def test_salvar_csv_vazio_cria_arquivo_vazio(self, tmp_path):
        caminho = tmp_path / "vazio.csv"

        limpeza.salvar_csv(caminho, [])

        assert caminho.read_text(encoding="utf-8") == ""

    def test_gravar_saidas(self, tmp_path, monkeypatch):
        monkeypatch.setattr(limpeza, "DIRETORIO_SAIDA", tmp_path)

        resultados = {
            "pagamentos": resultado_com([
                {"evento_id": "ev-001", "valor": Decimal("10.00")},
            ]),
            "tribunal": resultado_com([
                {"numero_processo": PROCESSO, "valor_face": Decimal("10.00")},
            ]),
        }
        relatorio = limpeza.montar_relatorio(resultados, [])

        limpeza.gravar_saidas(resultados, relatorio)

        assert (tmp_path / "pagamentos_limpos.json").exists()
        assert (tmp_path / "tribunal_limpos.csv").exists()
        assert (tmp_path / "relatorio_limpeza.json").exists()
        assert (tmp_path / "registros_descartados.json").exists()
        assert (tmp_path / "registros_pendentes.json").exists()

        pagamentos = json.loads(
            (tmp_path / "pagamentos_limpos.json").read_text(encoding="utf-8")
        )
        assert pagamentos[0]["valor"] == "10.00"


class TestCarregar:
    def test_carregar_csv_latin1_com_ponto_e_virgula(self, tmp_path):
        caminho = tmp_path / "tribunal.csv"
        caminho.write_bytes(
            "numero_processo;ente_devedor\n001;Município\n".encode("latin-1")
        )

        registros, delimitador = limpeza.carregar_csv(caminho)

        assert delimitador == ";"
        assert registros[0]["ente_devedor"] == "Município"

    def test_carregar_json_inexistente(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            limpeza.carregar_json(tmp_path / "nao_existe.json")
