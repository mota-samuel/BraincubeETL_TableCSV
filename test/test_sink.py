"""Testes da escrita do CSV (contrato e atomicidade)."""
from pathlib import Path

import pandas as pd
import pytest

import os

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

def test_substituir_com_retry_tenta_novamente_apos_travamento(tmp_path, monkeypatch):
    import os
    from src.sink import _substituir_com_retry
    replace_original = os.replace  # captura ANTES do patch
    origem = tmp_path / "a.csv.tmp"
    destino = tmp_path / "a.csv"
    origem.write_text("x", encoding="utf-8")

    chamadas = {"n": 0}

    def falso_replace(o, d):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise PermissionError(5, "Acesso negado")
        return replace_original(o, d)

    monkeypatch.setattr("src.sink.os.replace", falso_replace)
    monkeypatch.setattr("src.sink.time.sleep", lambda s: None)
    _substituir_com_retry(origem, destino)
    assert destino.exists() and chamadas["n"] == 2


def test_substituir_com_retry_exaure_com_mensagem_clara(tmp_path, monkeypatch):
    import pytest
    from src.sink import _substituir_com_retry
    origem = tmp_path / "b.csv.tmp"
    destino = tmp_path / "b.csv"
    origem.write_text("x", encoding="utf-8")

    def sempre_travado(o, d):
        raise PermissionError(5, "Acesso negado")

    monkeypatch.setattr("src.sink.os.replace", sempre_travado)
    monkeypatch.setattr("src.sink.time.sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="travado"):
        _substituir_com_retry(origem, destino)