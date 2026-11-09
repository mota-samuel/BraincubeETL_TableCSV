"""Testes do client com respostas simuladas."""
from unittest.mock import MagicMock

import pytest

from src.client import BraincubeClient, BraincubeError
from src.config import Settings


def _settings() -> Settings:
    return Settings(
        base_url="https://api.exemplo.mybraincube.com",
        braincube="exemplo",
        api_key="chave-teste",
    )


def _client_com_payload(payload: dict) -> BraincubeClient:
    client = BraincubeClient(_settings())
    resposta = MagicMock()
    resposta.status_code = 200
    resposta.json.return_value = payload
    client.session = MagicMock()
    client.session.get.return_value = resposta
    return client


def test_resolve_order_rejeita_payload_sem_order():
    client = _client_com_payload({"erro": "sem order"})
    with pytest.raises(BraincubeError, match="order"):
        client.resolve_order("mb14")


def test_resolve_order_faz_cache():
    client = _client_com_payload({"order": "d1400004 asc"})
    assert client.resolve_order("mb14") == "d1400004 asc"
    assert client.session.get.call_count == 1
    client.resolve_order("mb14")  # segunda chamada vem do cache
    assert client.session.get.call_count == 1