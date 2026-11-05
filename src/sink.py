"""Escrita do CSV de contrato."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import OutputSpec, Settings

log = logging.getLogger(__name__)


def prepare_output(df: pd.DataFrame, spec: OutputSpec) -> pd.DataFrame:
    faltando = [c for c in spec.columns if c not in df.columns]

    if faltando and not spec.allow_missing_columns:
        raise ValueError(
            f"o CSV perderia colunas do contrato: {faltando}. "
            "Ajuste rename, rules ou allow_missing_columns."
        )

    for coluna in faltando:
        log.warning("Coluna do contrato ausente, preenchida vazia: %s", coluna)
        df[coluna] = ""

    out = df[spec.columns].copy()

    for coluna in spec.date_only_columns:
        if coluna in out.columns:
            out[coluna] = pd.to_datetime(out[coluna], errors="coerce").dt.strftime(
                spec.date_format
            )

    for coluna in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[coluna]):
            out[coluna] = out[coluna].dt.strftime(spec.datetime_format)

    return out


def write_csv(df: pd.DataFrame, spec: OutputSpec, settings: Settings) -> Path:
    destino = Path(settings.data_dir) / "output" / spec.file
    destino.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(
        destino,
        index=False,
        sep=spec.delimiter,
        decimal=spec.decimal,
        encoding=spec.encoding,
        na_rep=spec.na_rep,
    )

    log.info("CSV gravado em %s (%d linhas)", destino.resolve(), len(df))
    return destino