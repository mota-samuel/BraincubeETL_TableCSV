"""Paridade das regras melt/parse_attribute/fillna com o M."""
import pandas as pd

from src.config import FillnaRule, MeltRule, ParseAttributeRule
from src.transform import apply_fillna, apply_melt, apply_parse_attribute


def test_melt_id_vars_sao_colunas_sem_separador():
    df = pd.DataFrame(
        {
            "Timestamp": ["a", "b"],
            "Indice": [1, 2],
            "10 - M1 - CAT - L1": [90.0, 80.0],
            "10 - CAT - L3": [70.0, 60.0],
        }
    )
    regra = MeltRule(type="melt", value_name="Valor")
    out = apply_melt(df, regra)
    assert list(out.columns) == ["Timestamp", "Indice", "Atributo", "Valor"]
    assert len(out) == 4
    assert set(out["Atributo"]) == {"10 - M1 - CAT - L1", "10 - CAT - L3"}


def test_parse_attribute_quatro_partes_com_maquina():
    df = pd.DataFrame({"Atributo": ["10 - M1 - CAT - L1"]})
    out = apply_parse_attribute(
        df, ParseAttributeRule(type="parse_attribute", source="Atributo")
    )
    assert out["Maquina"].iloc[0] == "M1"
    assert out["Linha"].iloc[0] == "L1"


def test_parse_attribute_maquina_vazia_vira_traco():
    df = pd.DataFrame({"Atributo": ["10 -  - CAT - L2"]})
    out = apply_parse_attribute(
        df, ParseAttributeRule(type="parse_attribute", source="Atributo")
    )
    assert out["Maquina"].iloc[0] == "-"
    assert out["Linha"].iloc[0] == "L2"


def test_parse_attribute_tres_partes_sem_maquina():
    df = pd.DataFrame({"Atributo": ["10 - CAT - L3"]})
    out = apply_parse_attribute(
        df, ParseAttributeRule(type="parse_attribute", source="Atributo")
    )
    assert out["Maquina"].iloc[0] == "-"
    assert out["Linha"].iloc[0] == "L3"


def test_parse_attribute_curto_gera_linha_nula():
    df = pd.DataFrame({"Atributo": ["sozinho"]})
    out = apply_parse_attribute(
        df, ParseAttributeRule(type="parse_attribute", source="Atributo")
    )
    assert out["Maquina"].iloc[0] == "-"
    assert pd.isna(out["Linha"].iloc[0])


def test_fillna_substitui_apenas_nan():
    df = pd.DataFrame({"Valor": [1.0, None]})
    out = apply_fillna(df, FillnaRule(type="fillna", columns=["Valor"], value=0))
    assert out["Valor"].tolist() == [1.0, 0]