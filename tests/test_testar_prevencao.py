import argparse
import os
import subprocess
import sys
from types import SimpleNamespace
import pytest
from scripts import testar_prevencao as tp

def _args(**kwargs):
    base = {
        "local": False,
        "container": "pgcase",
        "host": "localhost",
        "port": 5432,
        "user": "postgres",
        "password": None,
    }
    base.update(kwargs)
    return argparse.Namespace(**base)


def _resultado(returncode, stderr=""):
    return SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")


class TestMontarComando:
    def test_usa_podman_exec_no_container(self):
        comando = tp.montar_comando(_args(), "teste_prevencao")

        assert comando[:4] == ["podman", "exec", "-i", "pgcase"]
        assert comando[comando.index("-d") + 1] == "teste_prevencao"

    def test_usa_psql_local_com_porta(self):
        comando = tp.montar_comando(_args(local=True, port=5433), "teste_conflito")

        assert comando[0] == "psql"
        assert comando[comando.index("-p") + 1] == "5433"
        assert comando[comando.index("-d") + 1] == "teste_conflito"


class TestExecutar:
    def test_executa_com_sql_e_configura_senha(self, monkeypatch):
        chamada = {}

        def run(comando, **kwargs):
            chamada["comando"] = comando
            chamada["kwargs"] = kwargs
            return _resultado(0)

        monkeypatch.setattr(tp.subprocess, "run", run)

        resultado = tp.executar(
            _args(local=True, password="segredo"),
            "teste_prevencao",
            "SELECT 1",
        )

        assert resultado.returncode == 0
        assert chamada["comando"][-2:] == ["-c", "SELECT 1"]
        assert chamada["kwargs"]["env"]["PGPASSWORD"] == "segredo"

    def test_executa_com_entrada_sem_argumento_c(self, monkeypatch):
        chamada = {}

        def run(comando, **kwargs):
            chamada["comando"] = comando
            chamada["kwargs"] = kwargs
            return _resultado(0)

        monkeypatch.setattr(tp.subprocess, "run", run)

        tp.executar(_args(), "teste_prevencao", entrada="SELECT 2")

        assert chamada["comando"][-1] != "-c"
        assert chamada["kwargs"]["input"] == "SELECT 2"

    def test_comando_nao_encontrado_gera_falha(self, monkeypatch):
        def run(*args, **kwargs):
            raise FileNotFoundError(2, "Não encontrado", "psql")

        monkeypatch.setattr(tp.subprocess, "run", run)

        with pytest.raises(tp.Falha, match="comando não encontrado"):
            tp.executar(_args(local=True), "teste_prevencao", "SELECT 1")

    def test_erro_sem_permitir_erro_gera_falha(self, monkeypatch):
        monkeypatch.setattr(
            tp.subprocess,
            "run",
            lambda *args, **kwargs: _resultado(1, "senha inválida"),
        )

        with pytest.raises(tp.Falha, match="senha inválida"):
            tp.executar(_args(local=True), "postgres", "SELECT 1")


class TestConferir:
    def test_registra_acerto(self, capsys):
        resultados = []

        tp.conferir("tipo", "character varying(25)", "character varying(25)", resultados)

        assert resultados == [True]
        assert "PASS tipo" in capsys.readouterr().out

    def test_registra_erro(self, capsys):
        resultados = []

        tp.conferir("tipo", "character(20)", "character varying(25)", resultados)

        assert resultados == [False]
        saida = capsys.readouterr().out
        assert "FALHOU tipo" in saida
        assert "character(20)" in saida


class TestConsultaEBancos:
    def test_consultar_remove_espacos(self, monkeypatch):
        monkeypatch.setattr(
            tp,
            "executar",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout="  valor  \n",
                stderr="",
            ),
        )

        assert tp.consultar(_args(), "teste_prevencao", "SELECT 1") == "valor"

    def test_criar_banco_dropa_e_cria(self, monkeypatch):
        chamadas = []
        monkeypatch.setattr(
            tp,
            "executar",
            lambda args, banco, sql=None, **kwargs:
                chamadas.append((banco, sql)),
        )

        tp.criar_banco(_args(), "teste_prevencao")

        assert chamadas == [
            ("postgres", "DROP DATABASE IF EXISTS teste_prevencao"),
            ("postgres", "CREATE DATABASE teste_prevencao"),
        ]

    def test_remover_banco(self, monkeypatch):
        chamadas = []
        monkeypatch.setattr(
            tp,
            "executar",
            lambda args, banco, sql=None, **kwargs:
                chamadas.append((banco, sql)),
        )

        tp.remover_banco(_args(), "teste_conflito")

        assert chamadas == [
            ("postgres", "DROP DATABASE IF EXISTS teste_conflito"),
        ]


class TestVerificarRegra:
    def test_aceita_quando_esperado(self, monkeypatch):
        monkeypatch.setattr(tp, "executar", lambda *a, **k: _resultado(0))
        resultados = []

        tp.verificar_regra(_args(), "CNJ mascarado", "SQL", True, resultados)

        assert resultados == [True]

    def test_rejeita_quando_esperado(self, monkeypatch):
        monkeypatch.setattr(tp, "executar", lambda *a, **k: _resultado(1, "erro"))
        resultados = []

        tp.verificar_regra(_args(), "CNJ sem máscara", "SQL", False, resultados)

        assert resultados == [True]

    def test_falha_quando_resultado_inesperado(self, monkeypatch):
        monkeypatch.setattr(tp, "executar", lambda *a, **k: _resultado(1, "erro"))
        resultados = []

        tp.verificar_regra(_args(), "pagamento positivo", "SQL", True, resultados)

        assert resultados == [False]


class TestAplicarArquivo:
    def test_arquivo_ausente(self, tmp_path):
        with pytest.raises(tp.Falha, match="arquivo não encontrado"):
            tp.aplicar_arquivo(_args(), "teste", tmp_path / "nao_existe.sql")

    def test_aplica_conteudo_existente(self, tmp_path, monkeypatch):
        arquivo = tmp_path / "migracao.sql"
        arquivo.write_text("SELECT 1;", encoding="utf-8")
        chamada = {}

        def executar(args, banco, sql=None, entrada=None, permitir_erro=False):
            chamada.update(
                args=args,
                banco=banco,
                sql=sql,
                entrada=entrada,
                permitir_erro=permitir_erro,
            )

        monkeypatch.setattr(tp, "executar", executar)

        tp.aplicar_arquivo(_args(), "teste", arquivo)

        assert chamada["banco"] == "teste"
        assert chamada["entrada"] == "SELECT 1;"
        assert chamada["sql"] is None


class TestPrincipal:
    def test_falha_de_conexao_retorna_um(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["testar_prevencao.py"])

        def falhar(*args, **kwargs):
            raise tp.Falha("sem conexão")

        monkeypatch.setattr(tp, "executar", falhar)

        assert tp.principal() == 1
        assert "ERRO: sem conexão" in capsys.readouterr().out

    def test_fluxo_completo_retorna_zero(self, monkeypatch, capsys):
        monkeypatch.setattr(
            sys,
            "argv",
            ["testar_prevencao.py", "--keep"],
        )
        monkeypatch.setattr(tp, "executar", lambda *args, **kwargs: _resultado(0))
        monkeypatch.setattr(
            tp,
            "testar_banco_limpo",
            lambda args, resultados: resultados.append(True),
        )
        monkeypatch.setattr(
            tp,
            "testar_conflito",
            lambda args, resultados: resultados.append(True),
        )

        assert tp.principal() == 0
        saida = capsys.readouterr().out
        assert "2/2 verificações passaram" in saida


def _container_ativo(nome):
    try:
        resultado = subprocess.run(
            ["podman", "ps", "--filter", f"name={nome}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return nome in resultado.stdout.split()


@pytest.mark.skipif(
    not os.environ.get("CASE_PG_TESTE"),
    reason="defina CASE_PG_TESTE=1 para rodar contra o Postgres",
)
def test_integracao_com_postgres():
    container = os.environ.get("CASE_PG_CONTAINER", "pgcase")
    if not _container_ativo(container):
        pytest.skip(f"container {container} não está ativo")

    resultado = subprocess.run(
        [
            sys.executable,
            str(tp.RAIZ / "scripts" / "testar_prevencao.py"),
            "--container",
            container,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "FALHOU" not in resultado.stdout
