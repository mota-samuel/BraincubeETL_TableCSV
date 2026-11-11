"""Testes da compose: joins entre CSVs gerados por consultas."""
import pandas as pd
import pytest
import yaml

from src.compose import run_compose
from src.config import QueryConfig, Settings


def _yaml_origem(nome: str, arquivo_csv: str, ultima_coluna: str) -> dict:
    return {
        "name": nome,
        "data_source": "mb15",
        "output": {
            "file": arquivo_csv,
            "columns": ["Timestamp", "Linha", "Maquina", ultima_coluna],
        },
    }


def _yaml_compose() -> dict:
    return {
        "name": "fechamento_dia_mb15",
        "compose": {
            "keys": ["Timestamp", "Linha", "Maquina"],
            "base": {
                "query": "oee_dia_mb15",
                "column": "OEE - Dia Ajinomoto",
            },
            "joins": [
                {
                    "query": "disponibilidade_dia_mb15",
                    "column": "Disponibilidade - Dia Ajinomoto",
                    "rename": "Disponibilidade",
                }
            ],
        },
        "output": {
            "file": "fechamento_dia_mb15.csv",
            "columns": [
                "Timestamp",
                "Linha",
                "Maquina",
                "OEE - Dia Ajinomoto",
                "Disponibilidade",
            ],
            "sort": [{"column": "Timestamp", "ascending": False}],
        },
    }


def _settings(tmp_path) -> Settings:
    return Settings(
        base_url="https://api.exemplo.mybraincube.com",
        braincube="exemplo",
        api_key="chave-teste",
        data_dir=tmp_path / "data",
    )


def test_compose_junta_e_ordena_por_data(tmp_path, monkeypatch):
    saida = tmp_path / "data" / "output"
    saida.mkdir(parents=True)

    (saida / "oee.csv").write_text(
        "Timestamp;Linha;Maquina;OEE - Dia Ajinomoto\n"
        "31/12/2025 00:00:00;L1;M1;90\n"
        "01/01/2026 00:00:00;L1;M1;80\n",
        encoding="utf-8-sig",
    )
    (saida / "disp.csv").write_text(
        "Timestamp;Linha;Maquina;Disponibilidade - Dia Ajinomoto\n"
        "01/01/2026 00:00:00;L1;M1;95\n",
        encoding="utf-8-sig",
    )

    queries = tmp_path / "queries"
    queries.mkdir()
    especificos = {
        "oee_dia_mb15": _yaml_origem("oee_dia_mb15", "oee.csv", "OEE - Dia Ajinomoto"),
        "disponibilidade_dia_mb15": _yaml_origem(
            "disponibilidade_dia_mb15", "disp.csv", "Disponibilidade - Dia Ajinomoto"
        ),
        "fechamento_dia_mb15": _yaml_compose(),
    }
    for nome, conteudo in especificos.items():
        (queries / f"{nome}.yaml").write_text(
            yaml.safe_dump(conteudo, allow_unicode=True), encoding="utf-8"
        )
    monkeypatch.setattr("src.compose.QUERIES_DIR", queries)

    resultado = run_compose(QueryConfig(**_yaml_compose()), _settings(tmp_path))
    assert resultado["status"] == "ok"

    df = pd.read_csv(
        tmp_path / "data" / "output" / "fechamento_dia_mb15.csv",
        sep=";",
        decimal=",",
        encoding="utf-8-sig",
    )
    assert list(df.columns) == [
        "Timestamp",
        "Linha",
        "Maquina",
        "OEE - Dia Ajinomoto",
        "Disponibilidade",
    ]
    assert len(df) == 2
    # Ordenação desc por Timestamp (paridade com o M)
    assert df["Timestamp"].iloc[0] == "01/01/2026 00:00:00"
    assert df["Timestamp"].iloc[1] == "31/12/2025 00:00:00"
    # Linha sem correspondência no join fica NULA, não zero (paridade com o M)
    assert df["Disponibilidade"].iloc[0] == 95
    assert pd.isna(df["Disponibilidade"].iloc[1])


def test_compose_falha_amigavel_sem_csv_de_origem(tmp_path, monkeypatch):
    (tmp_path / "data" / "output").mkdir(parents=True)

    queries = tmp_path / "queries"
    queries.mkdir()
    (queries / "fechamento_mes_mb15.yaml").write_text(
        yaml.safe_dump(_yaml_compose(), allow_unicode=True), encoding="utf-8"
    )
    monkeypatch.setattr("src.compose.QUERIES_DIR", queries)

    with pytest.raises(FileNotFoundError, match="oee_dia_mb15"):
        run_compose(QueryConfig(**_yaml_compose()), _settings(tmp_path))