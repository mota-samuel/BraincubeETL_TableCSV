"""Composição: junta CSVs gerados por outras consultas (sem tocar na API)."""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from .config import PROJECT_ROOT, QueryConfig, Settings
from .sink import prepare_output, write_csv
from .transform import apply_sort

log = logging.getLogger(__name__)

QUERIES_DIR = PROJECT_ROOT / "config" / "queries"


def resolver_query(nome: str) -> QueryConfig:
    """Localiza o YAML de uma consulta em qualquer subpasta de queries."""
    encontrados = sorted(QUERIES_DIR.rglob(f"{nome}.yaml"))
    if not encontrados:
        raise FileNotFoundError(
            f"configuração não encontrada em {QUERIES_DIR}: {nome}.yaml"
        )
    if len(encontrados) > 1:
        lista = "\n".join(str(p) for p in encontrados)
        raise ValueError(f"nome de consulta duplicado na