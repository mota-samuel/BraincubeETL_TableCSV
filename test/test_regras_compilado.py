"""Paridade das regras de compilado (period_column e groupby) com o M."""
import pandas as pd

from src.config import GroupAgg, GroupByRule, PeriodColumnRule
from src.transform import apply_groupby, apply_period_column


def test_periodo_mensal_vira_primeiro_dia_do_mes():
    df = pd.DataFrame(
        {"Timestamp": pd.to_datetime(["2026-11-03 14:20:00", "2026-11-01 00:00:00"])}
    )
    out = apply_period_column(
        df,
        PeriodColumnRule(type="period_column", source="Timestamp", target="Mes"),
    )
    assert (out["Mes"] == pd.Timestamp("2026-11-01")).all()


def test_periodo_semanal_domingo_e_padrao_do_m():
    # 2026-11-04 é quarta; a semana com início no domingo começa em 01/11.
    df = pd.DataFrame({"Timestamp": pd.to_datetime(["2026-11-04 10:00:00"])})
    out = apply_period_column(
        df,
        PeriodColumnRule(
            type="period_column", source="Timestamp", target="Semana", period="week"
        ),
    )
    assert out["Semana"].iloc[0] == pd.Timestamp("2026-11-01")


def test_periodo_semanal_segunda_feira():
    df = pd.DataFrame({"Timestamp": pd.to_datetime(["2026-11-04 10:00:00"])})
    out = apply_period_column(
        df,
        PeriodColumnRule(
            type="period_column",
            source="Timestamp",
            target="Semana",
            period="week",
            week_start="monday",
        ),
    )
    assert out["Semana"].iloc[0] == pd.Timestamp("2026-11-02")


def test_groupby_soma_e_renomeia():
    df = pd.DataFrame(
        {
            "Mes": pd.to_datetime(["2026-11-01", "2026-11-01", "2026-12-01"]),
            "Linha": ["J", "J", "J"],
            "Maquina": ["BAL01", "BAL01", "BAL01"],
            "TR": [1.5, 2.5, 9.0],
        }
    )
    out = apply_groupby(
        df,
        GroupByRule(
            type="groupby",
            keys=["Mes", "Linha", "Maquina"],
            aggregations=[
                GroupAgg(column="TR", func="sum", output="TR Mensal")
            ],
        ),
    )
    assert list(out.columns) == ["Mes", "Linha", "Maquina", "TR Mensal"]
    assert len(out) == 2
    assert out["TR Mensal"].iloc[0] == 4.0