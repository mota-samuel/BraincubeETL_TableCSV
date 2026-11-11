"""Equivalente das transformações feitas nas consultas M."""
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


def apply_conditional_column(df: pd.DataFrame, rule) -> pd.DataFrame:
    """Réplica do AddColumn condicional do M.

    Paridade exata: no M, null = "" resulta False, então motivo NULO
    cai no else_value (mesmo comportamento do relatório atual).
    Se o negócio decidir que nulo conta como vazio, trocar a comparação
    por: valores = df[rule.source].astype("string").fillna("")
    """
    if rule.source not in df.columns:
        raise KeyError(f"coluna ausente para conditional_column: {rule.source}")

    valores = df[rule.source].astype("string")
    comparacao = valores.eq(str(rule.equals)).fillna(False)

    df[rule.target] = [
        rule.then_value if c else rule.else_value for c in comparacao
    ]
    log.info(
        "Coluna derivada %s a partir de %s: %d linhas = '%s'",
        rule.target,
        rule.source,
        int(comparacao.sum()),
        rule.then_value,
    )
    return df


def apply_melt(df: pd.DataFrame, rule) -> pd.DataFrame:
    """Réplica do UnpivotOtherColumns: ids = colunas SEM o separador."""
    ids = [c for c in df.columns if rule.separator not in c]
    atributos = [c for c in df.columns if c not in ids]
    if not atributos:
        raise ValueError(
            f"melt sem colunas de atributo: nenhuma coluna contém '{rule.separator}'"
        )

    df = df.melt(
        id_vars=ids, var_name=rule.attribute_name, value_name=rule.value_name
    )
    log.info("Melt: %d colunas de atributo -> %d linhas", len(atributos), len(df))
    return df


def apply_parse_attribute(df: pd.DataFrame, rule) -> pd.DataFrame:
    """Réplica do Parseia do M.

    4 partes: Indice - Maquina - Categoria - Linha -> Maquina=p1 (ou "-" se vazia), Linha=p3
    3 partes: com machine_min_parts=3, Maquina=p1 (ou "-"); senão Maquina="-"; Linha=p2
    Menos de 3 partes: Maquina="-", Linha=nula.
    """
    if rule.source not in df.columns:
        raise KeyError(f"coluna ausente para parse_attribute: {rule.source}")

    serie = df[rule.source].astype("string")
    partes = serie.str.split(rule.separator)
    qtde = partes.str.len().fillna(0)

    expandido = serie.str.split(rule.separator, expand=True)
    n_max = 0 if expandido is None else expandido.shape[1]

    # Paridade com o Text.Trim de cada parte no M.
    for i in range(n_max):
        expandido[i] = expandido[i].str.strip()

    def parte(i: int) -> pd.Series:
        if i < n_max:
            return expandido[i]
        return pd.Series(pd.NA, index=df.index, dtype="string")

    maquina = pd.Series("-", index=df.index, dtype="string")
    linha = pd.Series(pd.NA, index=df.index, dtype="string")

    mascara_maquina = qtde >= rule.machine_min_parts
    p1, p3 = parte(1), parte(3)
    com_maquina = mascara_maquina & p1.notna() & (p1 != "")
    maquina[com_maquina] = p1[com_maquina]

    mascara4 = qtde >= 4
    linha[mascara4] = p3[mascara4]

    mascara3 = qtde == 3
    linha[mascara3] = parte(2)[mascara3]

    df[rule.machine] = maquina
    df[rule.line] = linha
    df = df.drop(columns=[rule.source])
    log.info(
        "Parse de atributo: %d com maquina, %d com 3 partes (%d linhas)",
        int(com_maquina.sum()),
        int(mascara3.sum()),
        len(df),
    )
    return df


def apply_fillna(df: pd.DataFrame, rule) -> pd.DataFrame:
    """Substitui NaN por um valor fixo (paridade com o ReplaceValue NaN->0 do M)."""
    for coluna in rule.columns:
        if coluna not in df.columns:
            raise KeyError(f"coluna ausente para fillna: {coluna}")
        faltantes = int(df[coluna].isna().sum())
        df[coluna] = df[coluna].fillna(rule.value)
        log.info(
            "Fillna em %s: %d valores substituídos por %s",
            coluna,
            faltantes,
            rule.value,
        )
    return df


def apply_rules(df: pd.DataFrame, rules: list) -> pd.DataFrame:
    for rule in rules:
        if rule.type == "split_column":
            df = apply_split(df, rule)
        elif rule.type == "date_shift":
            df = apply_date_shift(df, rule)
        elif rule.type == "trim":
            df = apply_trim(df, rule)
        elif rule.type == "conditional_column":
            df = apply_conditional_column(df, rule)
        elif rule.type == "melt":
            df = apply_melt(df, rule)
        elif rule.type == "parse_attribute":
            df = apply_parse_attribute(df, rule)
        elif rule.type == "fillna":
            df = apply_fillna(df, rule)
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