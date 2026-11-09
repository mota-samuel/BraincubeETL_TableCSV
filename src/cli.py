"""Interface de linha de comando."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import logging_setup
from .client import BraincubeClient
from .config import PROJECT_ROOT, QueryConfig, Settings
from .dictionary import build_dictionary
from .pipeline import run_query

log = logging.getLogger(__name__)

# Caminhos ancorados na raiz do projeto: o ETL funciona igual quando
# executado manualmente, pelo agendador ou por CI, de qualquer diretório.
# ATENÇÃO: a pasta é "config/queries" (minúscula) — rodar o git mv indicado
# no fim deste pacote, pois o Linux/Docker/CI são case-sensitive.
SETTINGS_PADRAO = PROJECT_ROOT / "config" / "settings.yaml"
QUERIES_DIR = PROJECT_ROOT / "config" / "queries"


def _carregar_settings(caminho: str | None) -> Settings:
    return Settings.load(Path(caminho) if caminho else SETTINGS_PADRAO)


def _carregar_query(nome: str, caminho: str | None) -> QueryConfig:
    if caminho:
        return QueryConfig.load(Path(caminho))
    arquivo = QUERIES_DIR / f"{nome}.yaml"
    if not arquivo.exists():
        raise FileNotFoundError(f"configuração não encontrada: {arquivo}")
    return QueryConfig.load(arquivo)


def cmd_run(args: argparse.Namespace) -> int:
    settings = _carregar_settings(args.settings)
    resultado = run_query(_carregar_query(args.query, args.file), settings)
    log.info("Resultado: %s", resultado)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    arquivos = sorted(QUERIES_DIR.glob("*.yaml"))
    if not arquivos:
        print(f"Nenhuma consulta configurada em {QUERIES_DIR}")
        return 0
    for arquivo in arquivos:
        query = QueryConfig.load(arquivo)
        status = "habilitada" if query.enabled else "desabilitada"
        print(f"{arquivo.stem} | {query.name} | {query.data_source} | {status}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    settings = _carregar_settings(args.settings)
    query = _carregar_query(args.query, args.file)
    inicio, fim = query.window.resolve(settings.timezone)
    print(f"Consulta: {query.name}")
    print(f"Data source: {query.data_source}")
    print(f"Order: {query.order.mode}")
    print(f"Janela: {inicio} até {fim}")
    print(f"Definitions: {query.definitions.source}")
    print(f"Saída: {query.output.file} ({len(query.output.columns)} colunas)")
    print("Configuração válida.")
    return 0


def cmd_variables(args: argparse.Namespace) -> int:
    settings = _carregar_settings(args.settings)
    client = BraincubeClient(settings)
    dicionario = build_dictionary(
        client, args.data_source, ["standard", "local", "tag"]
    )
    if args.output:
        destino = Path(args.output)
        dicionario.to_excel(destino, index=False)
        print(f"Dicionário salvo em {destino.resolve()}")
    else:
        print(dicionario.to_string(index=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="braincube-etl")
    parser.add_argument("--settings", help="caminho do settings.yaml")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--log-file", help="arquivo de log adicional ao stdout")

    sub = parser.add_subparsers(dest="comando", required=True)

    p_run = sub.add_parser("run", help="executa uma consulta")
    p_run.add_argument("--query", required=True)
    p_run.add_argument("--file")
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list", help="lista as consultas configuradas")
    p_list.set_defaults(func=cmd_list)

    p_val = sub.add_parser("validate", help="valida a configuração sem executar")
    p_val.add_argument("--query", required=True)
    p_val.add_argument("--file")
    p_val.set_defaults(func=cmd_validate)

    p_var = sub.add_parser("variables", help="exporta variáveis de uma memory base")
    p_var.add_argument("--data-source", required=True, help="ex.: mb14")
    p_var.add_argument("--output", help="arquivo .xlsx de saída")
    p_var.set_defaults(func=cmd_variables)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    arquivo_log = Path(args.log_file) if args.log_file else None
    logging_setup.setup(
        getattr(logging, str(args.log_level).upper(), logging.INFO),
        log_file=arquivo_log,
    )
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        # exc_info garante o stack trace mesmo com log-level INFO em produção.
        log.error("Falha na execução: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())