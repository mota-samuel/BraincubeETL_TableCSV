"""Única porta de entrada para a API do Braincube."""
from __future__ import annotations

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Settings

log = logging.getLogger(__name__)


class BraincubeError(RuntimeError):
    pass


class BraincubeClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        retry = Retry(
            total=settings.max_retries,
            backoff_factor=settings.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=8)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "x-api-key": settings.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        self._order_cache: dict[str, str] = {}
        self._dict_cache: dict[str, list[dict]] = {}

    def _url(self, *parts: str) -> str:
        base = self.settings.base_url.rstrip("/")
        tail = "/".join(str(p).strip("/") for p in parts)
        return f"{base}/{tail}"

    def _handle(self, response: requests.Response, contexto: str) -> dict:
        if response.status_code >= 400:
            trecho = response.text[:300]
            raise BraincubeError(
                f"{contexto} falhou com HTTP {response.status_code}: {trecho}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise BraincubeError(f"{contexto} devolveu resposta não JSON") from exc

    def resolve_order(self, data_source: str) -> str:
        if data_source in self._order_cache:
            return self._order_cache[data_source]
        url = self._url(
            "braincube", self.settings.braincube, "braindata", data_source, "LF"
        )
        log.debug("Descobrindo order em %s", url)
        response = self.session.get(url, timeout=self.settings.timeout)
        payload = self._handle(response, f"descoberta de order de {data_source}")

        order = payload.get("order")
        if not isinstance(order, str) or not order.strip():
            raise BraincubeError(
                f"descoberta de order de {data_source} não retornou 'order' "
                f"válido: {str(payload)[:300]}"
            )
        self._order_cache[data_source] = order
        return order

    def fetch_data(
        self,
        data_source: str,
        definitions: list[str],
        filtro: dict,
        order: str,
    ) -> dict:
        url = self._url(
            "braincube", self.settings.braincube, "braindata", data_source, "LF"
        )
        body = {
            "order": order,
            "definitions": definitions,
            "context": {"dataSource": data_source, "filter": filtro},
        }
        log.info("Consultando %s com %d definitions", data_source, len(definitions))
        response = self.session.post(url, json=body, timeout=self.settings.timeout)
        return self._handle(response, f"consulta de dados de {data_source}")

    def variables_summary(self, data_source: str, mb_number: str) -> list[dict]:
        if data_source in self._dict_cache:
            return self._dict_cache[data_source]

        url = self._url(
            "braincube",
            self.settings.braincube,
            "braincube",
            "mb",
            mb_number,
            "variables",
            "summary",
        )
        log.debug("Lendo dicionário em %s", url)
        response = self.session.get(url, timeout=self.settings.timeout)
        payload = self._handle(response, f"dicionário de {data_source}")

        items = payload.get("items") or []
        self._dict_cache[data_source] = items
        return items
