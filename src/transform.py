"""Equivalente das transformações feitas na consulta M."""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)


def build_renames(columns: list[str], dictionary: pd.DataFrame) -> dict[str, str]:
    """Reproduz a renomeação defensiva com List.Accumulate."""
    existing = set(columns)
    alvos: set[str] = set()
    renames: dict[str, str] = {}

    if dictionary is None or dictionary.empty:
        return renames

    for _, row in dictionary.iterrows():
        nome = row.get("NomeAmigavel")
        if not isinstance(nome, str) or not nome:
            continue

        chave = row.get("IdTecnico")
        if chave in existing:
            coluna = chave
        elif row.get("Uuid") in existing:
            coluna = row["Uuid"]
        else:
            continue

        if coluna == nome:
            continue
        if nome in alvos or nome in existing:
            log.warning("Renomeação ignorada por colisão: %s -> %s", coluna, nome)
            continue

        alvos.add(nome)
        renames[coluna] = nome

    return renames


def _threshold_minutes(valor: str) -> int:
    partes = str(valor).split(":")
    if len(partes) < 2:
        raise ValueError(f"threshold inválido: {valor}")
    return int(partes[0]) * 60 + int(partes[1])


def apply_split(df: pd.DataFrame, rule) -> pd.DataFrame:
    if rule.column not in df.columns:
        raise KeyError(f"coluna ausente para split: {rule.column}")

    original = df[rule.column].astype("string")
    dividido = original.str.split(str(rule.delimiter), n=1, expand=True)

    if rule.keep >= dividido.shape[1]:
        nova = original
    else:
        nova = dividido[rule.keep].where(dividido[rule.keep].notna(), original)

    destino = rule.output or rule.column
    df[destino] = nova
    log.info("Split aplicado em %s pelo delimitador %s", rule.column, rule.delimiter)
    return df


def apply_date_shift(df: pd.DataFrame, rule) -> pd.DataFrame:
    if rule.source not in df.columns:
        raise KeyError(f"coluna ausente para date_shift: {rule.source}")

    dt = pd.to_datetime(df[rule.source], errors="coerce")
    limite = _threshold_minutes(rule.threshold)

    minutos = dt.dt.hour * 60 + dt.dt.minute
    vira = (minutos >= limite).fillna(False).astype(int)

    base = dt.dt.normalize()
    deslocamento = pd.to_timedelta(vira * rule.shift_days, unit="D")

    df[rule.target] = base + deslocamento
    df.loc[dt.isna(), rule.target] = pd.NaT
    log.info(
        "Data deslocada: %s -> %s, limite %s, %d linhas viradas",
        rule.source,
        rule.target,
        rule.threshold,
        int(vira.sum()),
    )
    return df


def apply_trim(df: pd.DataFrame, rule) -> pd.DataFrame:
    for coluna in rule.columns:
        if coluna in df.columns:
            df[coluna] = df[coluna].astype("string").str.strip()
    return df


def apply_rules(df: pd.DataFrame, rules: list) -> pd.DataFrame:
    for rule in rules:
        if rule.type == "split_column":
            df = apply_split(df, rule)
        elif rule.type == "date_shift":
            df = apply_date_shift(df, rule)
        elif rule.type == "trim":
            df = apply_trim(df, rule)
        else:
            raise ValueError(f"regra desconhecida: {rule.type}")
    return df


def apply_sort(df: pd.DataFrame, spec: list) -> pd.DataFrame:
    if not spec:
        return df

    colunas = [s.column for s in spec]
    ausentes = [c for c in colunas if c not in df.columns]
    if ausentes:
        raise KeyError(f"colunas de ordenação ausentes: {ausentes}")

    return df.sort_values(
        by=colunas,
        ascending=[s.ascending for s in spec],
        kind="mergesort",
    ).reset_index(drop=True)