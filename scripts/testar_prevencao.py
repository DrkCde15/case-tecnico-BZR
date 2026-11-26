#!/usr/bin/env python3
"""Testa a migração de prevenção em bancos temporários do PostgreSQL."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCHEMA = RAIZ / "schema.sql"
MIGRACAO = RAIZ / "migrations" / "001_prevencao.sql"

BANCO_LIMPO = "teste_prevencao"
BANCO_CONFLITO = "teste_conflito"


class Falha(Exception):
    """Erro que interrompe o teste com uma mensagem legível."""


def montar_comando(args, banco):
    """Monta o comando psql para o container ou para o host."""
    if not args.local:
        return [
            "podman", "exec", "-i", args.container,
            "psql", "-U", args.user, "-d", banco,
            "-v", "ON_ERROR_STOP=1", "-qAt",
        ]
    return [
        "psql", "-h", args.host, "-p", str(args.port),
        "-U", args.user, "-d", banco,
        "-v", "ON_ERROR_STOP=1", "-qAt",
    ]


def executar(args, banco, sql=None, entrada=None, permitir_erro=False):
    """Executa SQL e devolve o resultado do processo."""
    comando = montar_comando(args, banco)
    if entrada is None:
        comando = comando + ["-c", sql]
    ambiente = dict(os.environ)
    if args.password:
        ambiente["PGPASSWORD"] = args.password
    try:
        resultado = subprocess.run(
            comando,
            input=entrada,
            text=True,
            capture_output=True,
            env=ambiente,
        )
    except FileNotFoundError as erro:
        raise Falha(f"comando não encontrado: {erro.filename}") from erro
    if resultado.returncode != 0 and not permitir_erro:
        raise Falha(resultado.stderr.strip() or resultado.stdout.strip())
    return resultado


def aplicar_arquivo(args, banco, caminho):
    """Aplica um arquivo SQL inteiro em um banco."""
    if not caminho.exists():
        raise Falha(f"arquivo não encontrado: {caminho}")
    executar(args, banco, entrada=caminho.read_text(encoding="utf-8"))


def consultar(args, banco, sql):
    """Executa uma consulta e devolve o texto da primeira coluna."""
    return executar(args, banco, sql).stdout.strip()


def criar_banco(args, banco):
    """Recria um banco temporário vazio."""
    executar(args, "postgres", f"DROP DATABASE IF EXISTS {banco}")
    executar(args, "postgres", f"CREATE DATABASE {banco}")


def remover_banco(args, banco):
    """Remove um banco temporário."""
    executar(args, "postgres", f"DROP DATABASE IF EXISTS {banco}")


def conferir(descricao, obtido, esperado, resultados):
    """Compara o valor obtido com o esperado e registra o resultado."""
    if obtido == esperado:
        resultados.append(True)
        print(f"PASS {descricao}: {obtido}")
    else:
        resultados.append(False)
        print(f"FALHOU {descricao}: esperado {esperado!r}, obtido {obtido!r}")


def verificar_regra(args, descricao, sql, deve_passar, resultados):
    """Confere se uma instrução é aceita ou rejeitada pelo banco."""
    resultado = executar(args, BANCO_LIMPO, sql, permitir_erro=True)
    passou = resultado.returncode == 0
    if passou == deve_passar:
        resultados.append(True)
        acao = "aceitou" if passou else "rejeitou"
        print(f"PASS {acao} {descricao}")
    else:
        resultados.append(False)
        acao = "aceitou" if passou else "rejeitou"
        print(f"FALHOU {acao} {descricao}")
        if resultado.stderr:
            print(f"     {resultado.stderr.strip()}")


def testar_banco_limpo(args, resultados):
    """Aplica schema e migração e valida as regras em um banco novo."""
    print(f"\n== banco limpo ({BANCO_LIMPO}) ==")
    criar_banco(args, BANCO_LIMPO)
    aplicar_arquivo(args, BANCO_LIMPO, SCHEMA)
    aplicar_arquivo(args, BANCO_LIMPO, MIGRACAO)
    print("schema e migração aplicados")

    conferir(
        "tipo de numero_processo",
        consultar(
            args,
            BANCO_LIMPO,
            "SELECT data_type || '(' || coalesce(character_maximum_length::text, '') || ')' "
            "FROM information_schema.columns "
            "WHERE table_name = 'precatorio' AND column_name = 'numero_processo'",
        ),
        "character varying(25)",
        resultados,
    )

    regras = [
        (
            "CNJ mascarado",
            "INSERT INTO precatorio (numero_processo, ente_devedor, valor_face) "
            "VALUES ('0012345-10.2019.8.26.0053', 'X', 1)",
            True,
        ),
        (
            "CNJ sem máscara",
            "INSERT INTO precatorio (numero_processo, ente_devedor, valor_face) "
            "VALUES ('00234562120208260053', 'X', 1)",
            False,
        ),
        (
            "pagamento positivo",
            "INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em) "
            "VALUES (1, 'ev-1', 'pagamento', 10, '2025-01-01')",
            True,
        ),
        (
            "evento_id duplicado",
            "INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em) "
            "VALUES (1, 'ev-1', 'pagamento', 20, '2025-01-01')",
            False,
        ),
        (
            "estorno negativo",
            "INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em) "
            "VALUES (1, 'ev-2', 'estorno', -5, '2025-01-02')",
            True,
        ),
        (
            "estorno positivo",
            "INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em) "
            "VALUES (1, 'ev-3', 'estorno', 5, '2025-01-02')",
            False,
        ),
        (
            "pagamento negativo",
            "INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em) "
            "VALUES (1, 'ev-4', 'pagamento', -5, '2025-01-02')",
            False,
        ),
        (
            "importação nova",
            "INSERT INTO importacao (arquivo, hash_arquivo) "
            "VALUES ('a.json', repeat('a', 64))",
            True,
        ),
        (
            "hash repetido",
            "INSERT INTO importacao (arquivo, hash_arquivo) "
            "VALUES ('b.json', repeat('a', 64))",
            False,
        ),
        (
            "staging novo",
            "INSERT INTO pagamento_staging (importacao_id, evento_id, payload) "
            "VALUES (1, 'ev-1', '{}')",
            True,
        ),
        (
            "staging duplicado no arquivo",
            "INSERT INTO pagamento_staging (importacao_id, evento_id, payload) "
            "VALUES (1, 'ev-1', '{}')",
            False,
        ),
    ]
    for descricao, sql, deve_passar in regras:
        verificar_regra(args, descricao, sql, deve_passar, resultados)


def testar_conflito(args, resultados):
    """Confere que a migração desfaz tudo quando há conflito de conteúdo."""
    print(f"\n== banco com conflito ({BANCO_CONFLITO}) ==")
    criar_banco(args, BANCO_CONFLITO)
    aplicar_arquivo(args, BANCO_CONFLITO, SCHEMA)
    executar(
        args,
        BANCO_CONFLITO,
        "INSERT INTO precatorio (numero_processo, ente_devedor, valor_face) "
        "VALUES ('00000000000000000000', 'X', 1);"
        "INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em) VALUES "
        "(1, 'ev-1', 'pagamento', 10, '2025-01-01'),"
        "(1, 'ev-1', 'pagamento', 10, '2025-01-01'),"
        "(1, 'ev-2', 'pagamento', 10, '2025-01-01'),"
        "(1, 'ev-2', 'pagamento', 20, '2025-01-01')",
    )

    migracao = MIGRACAO.read_text(encoding="utf-8")
    resultado = executar(
        args, BANCO_CONFLITO, entrada=migracao, permitir_erro=True
    )
    if resultado.returncode != 0:
        resultados.append(True)
        print("PASS migração bloqueada pelo conflito")
    else:
        resultados.append(False)
        print("FALHOU migração aceitou o conflito")

    conferir(
        "rollback manteve o tipo antigo",
        consultar(
            args,
            BANCO_CONFLITO,
            "SELECT data_type || '(' || coalesce(character_maximum_length::text, '') || ')' "
            "FROM information_schema.columns "
            "WHERE table_name = 'precatorio' AND column_name = 'numero_processo'",
        ),
        "character(20)",
        resultados,
    )
    conferir(
        "rollback não criou importacao",
        consultar(
            args,
            BANCO_CONFLITO,
            "SELECT coalesce(to_regclass('public.importacao')::text, 'ausente')",
        ),
        "ausente",
        resultados,
    )
    conferir(
        "rollback não criou a constraint",
        consultar(
            args,
            BANCO_CONFLITO,
            "SELECT count(*) FROM pg_constraint WHERE conname = 'uq_pagamento_evento'",
        ),
        "0",
        resultados,
    )
    conferir(
        "rollback manteve as duplicatas",
        consultar(
            args,
            BANCO_CONFLITO,
            "SELECT string_agg(evento_id || 'x' || total, ',' ORDER BY evento_id) "
            "FROM (SELECT evento_id, count(*) AS total FROM pagamento GROUP BY evento_id) t",
        ),
        "ev-1x2,ev-2x2",
        resultados,
    )

    executar(
        args,
        BANCO_CONFLITO,
        "DELETE FROM pagamento WHERE evento_id = 'ev-2' AND valor = 20",
    )
    aplicar_arquivo(args, BANCO_CONFLITO, MIGRACAO)

    conferir(
        "migração reaplicada após corrigir o conflito",
        consultar(
            args,
            BANCO_CONFLITO,
            "SELECT data_type || '(' || coalesce(character_maximum_length::text, '') || ')' "
            "FROM information_schema.columns "
            "WHERE table_name = 'precatorio' AND column_name = 'numero_processo'",
        ),
        "character varying(25)",
        resultados,
    )
    conferir(
        "constraint criada",
        consultar(
            args,
            BANCO_CONFLITO,
            "SELECT count(*) FROM pg_constraint WHERE conname = 'uq_pagamento_evento'",
        ),
        "1",
        resultados,
    )
    conferir(
        "duplicata idêntica removida",
        consultar(
            args,
            BANCO_CONFLITO,
            "SELECT string_agg(evento_id || 'x' || total, ',' ORDER BY evento_id) "
            "FROM (SELECT evento_id, count(*) AS total FROM pagamento GROUP BY evento_id) t",
        ),
        "ev-1x1,ev-2x1",
        resultados,
    )


def principal():
    """Lê os argumentos, executa os testes e devolve o código de saída."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--container",
        default="pgcase",
        help="container do PostgreSQL a usar via podman exec (padrão: pgcase)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="usa o psql do host em vez do container",
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default=None)
    parser.add_argument(
        "--keep",
        action="store_true",
        help="mantém os bancos de teste para inspeção",
    )
    args = parser.parse_args()

    resultados = []
    try:
        executar(args, "postgres", "SELECT 1")
        testar_banco_limpo(args, resultados)
        testar_conflito(args, resultados)
    except Falha as erro:
        print(f"\nERRO: {erro}")
        return 1
    finally:
        if not args.keep:
            for banco in (BANCO_LIMPO, BANCO_CONFLITO):
                try:
                    remover_banco(args, banco)
                except Falha:
                    pass

    total = len(resultados)
    aprovados = sum(resultados)
    print(f"\n{aprovados}/{total} verificações passaram")
    return 0 if aprovados == total else 1


if __name__ == "__main__":
    sys.exit(principal())
