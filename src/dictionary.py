"""Equivalente Python de fx_dictionary."""
from __future__ import annotations

import logging

import pandas as pd

from .client import BraincubeClient

log = logging.getLogger(__name__)


def mb_number(data_source: str) -> str:
    """Reproduz Text.AfterDelimiter(mb, 'mb')."""
    idx = data_source.find("mb")
    if idx < 0:
        raise ValueError(f"data_source sem prefixo 'mb': {data_source}")
    return data_source[idx + 2 :]


def build_dictionary(
    client: BraincubeClient,
    data_source: str,
    priority: list[str],
) -> pd.DataFrame:
    numero = mb_number(data_source)
    items = client.variables_summary(data_source, numero)

    registros = []
    for item in items:
        bc_id = item.get("bcId")
        if bc_id is None:
            continue

        nome = None
        for campo in priority:
            valor = item.get(campo)
            if valor not in (None, ""):
                nome = str(valor).strip()
                break
        if not nome:
            nome = str(item.get("tag") or f"var_{bc_id}").strip()

        registros.append(
            {
                "IdTecnico": f"{data_source}/d{bc_id}",
                "Uuid": item.get("uuid"),
                "NomeAmigavel": nome,
                "TipoBraincube": item.get("type"),
            }
        )

    df = pd.DataFrame(registros)
    if df.empty:
        log.warning("Dicionário vazio para %s", data_source)
    return df


def resolve_definitions(
    spec,
    client: BraincubeClient,
    dictionary: pd.DataFrame | None,
) -> list[str]:
    """Devolve a lista de definitions na ordem, sem duplicatas."""
    if spec.source == "list":
        valores = list(spec.values)

    elif spec.source == "file":
        if spec.path is None:
            raise ValueError("definitions.source=file exige o campo path")
        caminho = spec.path
        if not caminho.exists():
            raise FileNotFoundError(
                f"arquivo de definitions não encontrado: {caminho}"
            )
        if caminho.suffix.lower() in {".xlsx", ".xls"}:
            df = pd.read_excel(caminho)
        else:
            df = pd.read_csv(caminho, dtype=str, sep=None, engine="python")

        if spec.column not in df.columns:
            raise KeyError(
                f"coluna {spec.column} ausente em {caminho}. "
                f"Colunas disponíveis: {list(df.columns)}"
            )
        valores = df[spec.column].tolist()

    elif spec.source == "dictionary":
        if dictionary is None or dictionary.empty:
            raise ValueError(
                "definitions.source=dictionary exige dicionário carregado"
            )
        if "Uuid" in dictionary.columns:
            valores = dictionary["Uuid"].tolist()
        else:
            raise KeyError("dicionário sem coluna Uuid")

    else:
        raise ValueError(f"origem de definitions inválida: {spec.source}")

    limpos: list[str] = []
    vistos: set[str] = set()
    for valor in valores:
        if valor is None:
            continue
        if pd.isna(valor):
            continue
        texto = str(valor).strip()
        if not texto or texto in vistos:
            continue
        vistos.add(texto)
        limpos.append(texto)

    if spec.limit is not None:
        limpos = limpos[: spec.limit]

    if not limpos:
        raise ValueError("lista de definitions vazia após limpeza")

    log.info("Definitions resolvidas: %d", len(limpos))
    return limpos