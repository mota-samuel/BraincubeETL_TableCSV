"""Testes de Settings.load — teriam pego o bug C2 na esteira."""
from pathlib import Path

import pytest

from src.config import PROJECT_ROOT, QueryConfig, Settings


def _arquivo_settings(tmp_path: Path, extra: str = "") -> Path:
    arquivo = tmp_path / "settings.yaml"
    arquivo.write_text(
        "base_url: https://api.exemplo.mybraincube.com\n"
        "braincube: exemplo\n" + extra,
        encoding="utf-8",
    )
    return arquivo


def test_injeta_api_key_do_ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.load_dotenv", lambda: None)  # isola do .env real
    monkeypatch.setenv("BRAINCUBE_API_KEY", "chave-teste")
    settings = Settings.load(_arquivo_settings(tmp_path))
    assert settings.api_key == "chave-teste"


def test_falha_sem_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.load_dotenv", lambda: None)
    monkeypatch.delenv("BRAINCUBE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="BRAINCUBE_API_KEY"):
        Settings.load(_arquivo_settings(tmp_path))


def test_data_dir_relativo_ancora_na_raiz(tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.load_dotenv", lambda: None)
    monkeypatch.setenv("BRAINCUBE_API_KEY", "chave-teste")
    settings = Settings.load(_arquivo_settings(tmp_path, "data_dir: data\n"))
    assert settings.data_dir == PROJECT_ROOT / "data"


def test_query_ancora_input_relativo_na_raiz(tmp_path):
    arquivo = tmp_path / "q.yaml"
    arquivo.write_text(
        "name: teste\ndata_source: mb14\n"
        "definitions:\n  source: file\n  path: config/inputs/grupo_variables.csv\n"
        "output:\n  file: teste.csv\n  columns: [X]\n",
        encoding="utf-8",
    )
    query = QueryConfig.load(arquivo)
    assert query.definitions.path == (
        PROJECT_ROOT / "config" / "inputs" / "grupo_variables.csv"
    )