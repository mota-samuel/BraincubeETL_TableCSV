"""Composição: junta CSVs gerados por outras consultas (sem tocar na API)."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import PROJECT_ROOT, QueryConfig, Settings
from .sink import prepare_output, write_csv
from .transform import apply_sort

log = logging.getLogger(__name__)

QUERIES_DIR = PROJECT_ROOT / "config" / "queries"

# Chaves de join cujo nome sugere data são parseadas com o formato da
# origem, para o sort cronológico e o match correto no merge.
_DICAS_DATA = ("timestamp", "data", "date", "hora")


def resolver_query(nome: str) -> QueryConfig:
    """Localiza o YAML de uma consulta em qualquer subpasta de queries."""
    encontrados = sorted(QUERIES_DIR.rglob(f"{nome}.yaml"))
    if not encontrados:
        raise FileNotFoundError(
            f"configuração não encontrada em {QUERIES_DIR}: {nome}.yaml"
        )
    if len(encontrados) > 1:
        lista = "\n".join(str(p) for p in encontrados)
        raise ValueError(f"nome de consulta duplicado na árvore:\n{lista}")
    return QueryConfig.load(encontrados[0])


def _ler_csv_origem(origem: QueryConfig, settings: Settings) -> pd.DataFrame:
    caminho = Path(settings.data_dir) / "output" / origem.output.file
    if not caminho.exists():
        raise FileNotFoundError(
            f"CSV de origem ausente: {caminho} — execute a consulta "
            f"'{origem.name}' antes desta compose"
        )
    return pd.read_csv(
        caminho,
        sep=origem.output.delimiter,
        decimal=origem.output.decimal,
        encoding=origem.output.encoding,
    )


def _parsear_datas(df: pd.DataFrame, colunas: list[str], formato: str) -> pd.DataFrame:
    for coluna in colunas:
        if any(dica in coluna.lower() for dica in _DICAS_DATA):
            df[coluna] = pd.to_datetime(df[coluna], format=formato, errors="coerce")
    return df


def _carregar_entrada(entrada, keys: list[str], settings: Settings) -> pd.DataFrame:
    """Réplica do Preparar do M: reduz a {keys, coluna} e renomeia a métrica."""
    origem = resolver_query(entrada.query)
    df = _ler_csv_origem(origem, settings)

    faltantes = [c for c in [*keys, entrada.column] if c not in df.columns]
    if faltantes:
        raise KeyError(
            f"colunas ausentes no CSV da consulta '{origem.name}': {faltantes}; "
            f"contrato dela: {origem.output.columns}"
        )

    df = df[keys + [entrada.column]].copy()
    df = _parsear_datas(df, keys, origem.output.datetime_format)

    if entrada.rename and entrada.rename != entrada.column:
        df = df.rename(columns={entrada.column: entrada.rename})

    log.info("Entrada carregada: %s (%d linhas)", entrada.query, len(df))
    return df


def run_compose(query: QueryConfig, settings: Settings) -> dict:
    """Executa a composição declarada no bloco compose do YAML."""
    spec = query.compose
    if spec is None:
        raise ValueError(f"consulta {query.name} sem bloco compose")

    inicio = datetime.now()
    log.info("=== Início compose %s ===", query.name)

    df = _carregar_entrada(spec.base, spec.keys, settings)
    for entrada in spec.joins:
        outro = _carregar_entrada(entrada, spec.keys, settings)
        antes = len(df)
        df = df.merge(outro, on=spec.keys, how="left")
        log.info("Join left com %s: %d -> %d linhas", entrada.query, antes, len(df))

    df = apply_sort(df, query.output.sort)
    df = prepare_output(df, query.output)
    destino = write_csv(df, query.output, settings)

    duracao = (datetime.now() - inicio).total_seconds()
    log.info("=== Fim compose %s em %.1fs ===", query.name, duracao)
    return {
        "status": "ok",
        "linhas": len(df),
        "colunas": len(df.columns),
        "arquivo": str(destino),
        "duracao_s": round(duracao, 1),
    }