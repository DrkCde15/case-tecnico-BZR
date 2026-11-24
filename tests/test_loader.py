import json

import pytest

from loader import load_csv, load_json


class TestLoadJson:
    def test_le_json_utf8(self, tmp_path):
        arquivo = tmp_path / "dados.json"
        arquivo.write_text('[{"ente": "União"}]', encoding="utf-8")

        assert load_json(arquivo) == [{"ente": "União"}]

    def test_ignora_bom_utf8(self, tmp_path):
        arquivo = tmp_path / "dados.json"
        arquivo.write_text('[{"valor": 1}]', encoding="utf-8-sig")

        assert load_json(arquivo) == [{"valor": 1}]

    def test_arquivo_inexistente(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_json(tmp_path / "nao_existe.json")


class TestLoadCsv:
    def test_csv_utf8_com_virgula(self, tmp_path):
        arquivo = tmp_path / "dados.csv"
        arquivo.write_text(
            "processo,ente\n0012345-10.2019.8.26.0053,Município de São Paulo\n",
            encoding="utf-8",
        )

        df = load_csv(arquivo)

        assert df.attrs["delimiter"] == ","
        assert df.attrs["encoding"] == "utf-8"
        assert df.loc[0, "ente"] == "Município de São Paulo"

    def test_csv_latin1_com_ponto_e_virgula(self, tmp_path):
        conteudo = "numero_processo;ente_devedor\n001;Município de São Paulo\n"
        arquivo = tmp_path / "dados.csv"
        arquivo.write_bytes(conteudo.encode("latin-1"))

        df = load_csv(arquivo)

        assert df.attrs["delimiter"] == ";"
        assert df.attrs["encoding"] == "latin-1"
        assert df.loc[0, "ente_devedor"] == "Município de São Paulo"

    def test_remove_espacos_de_cabecalho_e_valores(self, tmp_path):
        arquivo = tmp_path / "dados.csv"
        arquivo.write_text(" ente , valor \n  União  ,  100 \n", encoding="utf-8")

        df = load_csv(arquivo)

        assert list(df.columns) == ["ente", "valor"]
        assert df.loc[0, "ente"] == "União"
        assert df.loc[0, "valor"] == "100"

    def test_csv_vazio_gera_dataframe_sem_linhas(self, tmp_path):
        arquivo = tmp_path / "vazio.csv"
        arquivo.write_text("", encoding="utf-8")

        df = load_csv(arquivo)

        assert df.empty
