"""Orquestração de uma consulta."""
from __future__ import annotations

import logging
from datetime import datetime

from .client import BraincubeClient
from Config import QueryConfig, Settings
from .dictionary import build_dictionary, resolve_definitions
from .fetch import build_frame
from .sink import prepare_output, write_csv
from .transform import apply_renames, apply_rules, apply_sort, build_renames

log = logging.getLogger(__name__)


def _substituir(obj, mapa: dict[str, str]):
    if isinstance(obj, str):
        return mapa.get(obj, obj)
    if isinstance(obj, list):
        return [_substituir(item, mapa) for item in obj]
    if isinstance(obj, dict):
        return {chave: _substituir(valor, mapa) for chave, valor in obj.items()}
    return obj


def run_query(query: QueryConfig, settings: Settings) -> dict:
    if not query.enabled:
        log.warning("Consulta %s desabilitada, ignorando", query.name)
        return {"status": "skipped"}

    inicio = datetime.now()
    log.info("=== Início %s ===", query.name)

    client = BraincubeClient(settings)

    if query.order.mode == "fixed":
        if not query.order.value:
            raise ValueError("order.mode=fixed exige order.value")
        order = query.order.value
    else:
        order = client.resolve_order(query.data_source)

    dictionary = None
    if query.rename.enabled or query.definitions.source == "dictionary":
        dictionary = build_dictionary(client, query.data_source, query.rename.priority)

    definitions = resolve_definitions(query.definitions, client, dictionary)

    janela_inicio, janela_fim = query.window.resolve(settings.timezone)
    filtro = _substituir(
        query.filter,
        {"{window.start}": janela_inicio, "{window.end}": janela_fim},
    )
    log.info("Janela aplicada: %s até %s", janela_inicio, janela_fim)

    payload = client.fetch_data(query.data_source, definitions, filtro, order)
    defs = payload.get("datadefs") or []

    df = build_frame(defs)
    if df.empty:
        log.warning("Consulta %s não retornou dados", query.name)
        return {"status": "empty", "linhas": 0}

    if dictionary is not None:
        renames = build_renames(list(df.columns), dictionary)
        if renames:
            df = df.rename(columns=renames)
            log.info("%d colunas renomeadas", len(renames))

    df = apply_rules(df, query.rules)
    df = apply_sort(df, query.output.sort)
    df = prepare_output(df, query.output)
    destino = write_csv(df, query.output, settings)

    duracao = (datetime.now() - inicio).total_seconds()
    log.info("=== Fim %s em %.1fs ===", query.name, duracao)

    return {
        "status": "ok",
        "linhas": len(df),
        "colunas": len(df.columns),
        "arquivo": str(destino),
        "duracao_s": round(duracao, 1),
    }