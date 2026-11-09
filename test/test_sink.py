"""Testes da escrita do CSV (contrato e atomicidade)."""
from pathlib import Path

import pandas as pd
import pytest

from src.config import OutputSpec, Settings
from src.sink import prepare_output, write_csv


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        base_url="https://api.exemplo.mybraincube.com",
        braincube="exemplo",
        api_key="chave-teste",
        data_dir=tmp_path,
    )


def test_write_csv_cria_arquivo_e_nao_deixa_tmp(tmp_path):
    df = pd.DataFrame({"Data Inicio": ["05/11/2026 08:00:00"]})
    spec = OutputSpec(file="saida.csv", columns=["Data Inicio"])

    destino = write_csv(df, spec, _settings(tmp_path))

    assert destino.exists()
    assert not Path(str(destino) + ".tmp").exists()
    assert destino.read_text(encoding="utf-8-sig").splitlines()[0] == "Data Inicio"


def test_prepare_output_falha_sem_coluna_do_contrato():
    df = pd.DataFrame({"Outra": [1]})
    spec = OutputSpec(file="x.csv", columns=["Data Inicio"])
    with pytest.raises(ValueError, match="contrato"):
        prepare_output(df, spec)