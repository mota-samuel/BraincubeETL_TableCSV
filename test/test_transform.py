"""Testes das regras que precisam manter paridade com o Power Query."""
from datetime import date

import pandas as pd
import pytest

from src.transform import (
    apply_date_shift,
    apply_rules,
    apply_sort,
    build_renames,
)
from src.config import DateShiftRule, SplitColumnRule
from src.fetch import build_frame

from .transform import apply_rules, apply_sort, build_renames


def test_rename_pula_colisao_com_coluna_existente():
    df_colunas = ["mb14/d1", "Data Inicio"]
    dicionario = pd.DataFrame(
        [
            {"IdTecnico": "mb14/d1", "Uuid": "u1", "NomeAmigavel": "Data Inicio"},
            {"IdTecnico": "mb14/d2", "Uuid": "u2", "NomeAmigavel": "Turno"},
        ]
    )
    renames = build_renames(df_colunas, dicionario)
    assert renames == {}


def test_rename_nao_duplica_alvo():
    colunas = ["mb14/d1", "mb14/d2"]
    dicionario = pd.DataFrame(
        [
            {"IdTecnico": "mb14/d1", "Uuid": "u1", "NomeAmigavel": "Status"},
            {"IdTecnico": "mb14/d2", "Uuid": "u2", "NomeAmigavel": "Status"},
        ]
    )
    renames = build_renames(colunas, dicionario)
    assert renames == {"mb14/d1": "Status"}


def test_rename_aceita_uuid_como_chave():
    colunas = ["uuid-abc"]
    dicionario = pd.DataFrame(
        [{"IdTecnico": "mb14/d1", "Uuid": "uuid-abc", "NomeAmigavel": "Turno"}]
    )
    renames = build_renames(colunas, dicionario)
    assert renames == {"uuid-abc": "Turno"}


def test_data_oee_avanca_apos_2220():
    df = pd.DataFrame(
        {
            "Data Inicio": pd.to_datetime(
                ["2026-11-05 22:19:00", "2026-11-05 22:20:00", "2026-11-05 08:00:00"]
            )
        }
    )
    regra = DateShiftRule(type="date_shift", source="Data Inicio", target="Data OEE")
    out = apply_date_shift(df, regra)
    assert out.loc[0, "Data OEE"].date() == date(2026, 11, 5)
    assert out.loc[1, "Data OEE"].date() == date(2026, 11, 6)
    assert out.loc[2, "Data OEE"].date() == date(2026, 11, 5)


def test_data_oee_preserva_nulo():
    df = pd.DataFrame({"Data Inicio": [pd.NaT]})
    regra = DateShiftRule(type="date_shift", source="Data Inicio", target="Data OEE")
    out = apply_date_shift(df, regra)
    assert pd.isna(out.loc[0, "Data OEE"])


def test_split_mantem_valor_sem_delimitador():
    df = pd.DataFrame({"Máquina": ["L1#EXTRA", "L2"]})
    regra = SplitColumnRule(type="split_column", column="Máquina", delimiter="#")
    out = apply_rules(df, [regra])
    assert list(out["Máquina"]) == ["L1", "L2"]


def test_build_frame_rejeita_tamanhos_divergentes():
    defs = [
        {"id": "a", "type": "NUMERIC", "data": [1, 2]},
        {"id": "b", "type": "NUMERIC", "data": [1]},
    ]
    with pytest.raises(ValueError):
        build_frame(defs)


def test_build_frame_converte_infinito_em_nulo():
    defs = [{"id": "a", "type": "NUMERIC", "data": ["1", "Infinity", "x"]}]
    df = build_frame(defs)
    assert df["a"].iloc[0] == 1
    assert pd.isna(df["a"].iloc[1])
    assert pd.isna(df["a"].iloc[2])


def test_sort_desc_preserva_ordem_esperada():
    df = pd.DataFrame({"Data Inicio": pd.to_datetime(["2026-01-01", "2026-03-01"])})

    class S:
        column = "Data Inicio"
        ascending = False

    out = apply_sort(df, [S()])
    assert out["Data Inicio"].iloc[0] == pd.Timestamp("2026-03-01")