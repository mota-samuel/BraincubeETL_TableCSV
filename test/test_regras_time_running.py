"""Paridade do parse_attribute com machine_min_parts (consulta Time Running)."""
import pandas as pd

from src.config import ParseAttributeRule
from src.transform import apply_parse_attribute


def _regra(**kwargs) -> ParseAttributeRule:
    return ParseAttributeRule(type="parse_attribute", source="Atributo", **kwargs)


def test_tres_partes_extrai_maquina_da_parte_2():
    df = pd.DataFrame({"Atributo": ["Tempo Running Dia Ajinomoto - BAL01 - Linha J"]})
    out = apply_parse_attribute(df, _regra(machine_min_parts=3))
    assert out["Maquina"].iloc[0] == "BAL01"
    assert out["Linha"].iloc[0] == "Linha J"


def test_quatro_partes_mantem_regra_da_parte_2_com_minimo_3():
    df = pd.DataFrame({"Atributo": ["10 - M1 - CAT - L1"]})
    out = apply_parse_attribute(df, _regra(machine_min_parts=3))
    assert out["Maquina"].iloc[0] == "M1"
    assert out["Linha"].iloc[0] == "L1"


def test_tres_partes_com_maquina_vazia_vira_traco():
    df = pd.DataFrame({"Atributo": ["Grupo -  - Linha K"]})
    out = apply_parse_attribute(df, _regra(machine_min_parts=3))
    assert out["Maquina"].iloc[0] == "-"
    assert out["Linha"].iloc[0] == "Linha K"


def test_padrao_4_preservado_para_consultas_anteriores():
    df = pd.DataFrame({"Atributo": ["10 - CAT - L3"]})
    out = apply_parse_attribute(df, _regra())
    assert out["Maquina"].iloc[0] == "-"
    assert out["Linha"].iloc[0] == "L3"


def test_trim_das_partes_paria_com_text_trim_do_m():
    df = pd.DataFrame({"Atributo": ["Grupo -  BAL01  - Linha J"]})
    out = apply_parse_attribute(df, _regra(machine_min_parts=3))
    assert out["Maquina"].iloc[0] == "BAL01"
    assert out["Linha"].iloc[0] == "Linha J"