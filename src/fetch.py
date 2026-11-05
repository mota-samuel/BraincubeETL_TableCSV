"""Consulta e montagem do DataFrame bruto."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .config import DATE_FMT

log = logging.getLogger(__name__)


def build_frame(defs: list[dict]) -> pd.DataFrame:
    if not defs:
        log.warning("datadefs vazio, retornando DataFrame vazio")
        return pd.DataFrame()

    colunas: list[str] = []
    series: list[list] = []
    tamanhos: set[int] = set()

    for item in defs:
        dados = item.get("data") or []
        tamanhos.add(len(dados))
        colunas.append(str(item["id"]))
        series.append(dados)

    if len(tamanhos) > 1:
        raise ValueError(
            f"datadefs com tamanhos divergentes: {sorted(tamanhos)}. "
            "O Power Query falharia em Table.FromColumns neste caso."
        )

    df = pd.DataFrame(dict(zip(colunas, series)))

    for item in defs:
        cid = str(item["id"])
        tipo = str(item.get("type") or "TEXT").upper()

        if tipo == "DATETIME":
            df[cid] = pd.to_datetime(df[cid], format=DATE_FMT, errors="coerce")
            invalidos = int(df[cid].isna().sum())
            if invalidos:
                log.warning("%s: %d datas não convertidas", cid, invalidos)
        elif tipo == "NUMERIC":
            df[cid] = pd.to_numeric(df[cid], errors="coerce").replace(
                [np.inf, -np.inf], np.nan
            )
        else:
            df[cid] = df[cid].astype("object")

    return df