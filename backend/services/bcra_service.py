from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import requests

from backend.core.config import settings



def clean_doc(doc: str) -> str:
    return re.sub(r"\D", "", doc or "")


class BCRAClient:
    _memory_cache: Dict[str, tuple[dict[str, Any], datetime]] = {}
    _cache_lock = threading.Lock()

    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout or settings.bcra_timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "LumenAnalitica-Backend/1.0",
                "Accept": "application/json",
            }
        )

    def _get(self, path: str, cache_ttl_min: int = 10) -> dict[str, Any]:
        url = f"{settings.bcra_base_url.rstrip('/')}/{path.lstrip('/')}"
        with self._cache_lock:
            if url in self._memory_cache:
                data, timestamp = self._memory_cache[url]
                if datetime.now() < timestamp + timedelta(minutes=cache_ttl_min):
                    return data

        for attempt in range(3):
            try:
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 200:
                    raw = response.json()
                    result = raw.get("results", {})
                    with self._cache_lock:
                        self._memory_cache[url] = (result, datetime.now())
                    return result
                if response.status_code == 404:
                    return {}
                if response.status_code == 429:
                    time.sleep((2 ** attempt) + 1)
                    continue
                return {}
            except requests.RequestException:
                time.sleep(1)
        return {}

    def get_deudas(self, identificacion: str) -> dict[str, Any]:
        return self._get(f"/CentralDeDeudores/v1.0/Deudas/{clean_doc(identificacion)}")

    def get_historicas(self, identificacion: str) -> dict[str, Any]:
        return self._get(f"/CentralDeDeudores/v1.0/Deudas/Historicas/{clean_doc(identificacion)}")

    def get_cheques_rechazados(self, identificacion: str) -> dict[str, Any]:
        return self._get(f"/CentralDeDeudores/v1.0/Deudas/ChequesRechazados/{clean_doc(identificacion)}")

    def get_entidades(self) -> List[Dict[str, Any]]:
        result = self._get("/cheques/v1.0/entidades", cache_ttl_min=60)
        return result if isinstance(result, list) else []

    def get_cheque_denunciado(self, codigo_entidad: int, numero_cheque: int) -> dict[str, Any]:
        return self._get(f"/cheques/v1.0/denunciados/{codigo_entidad}/{numero_cheque}", cache_ttl_min=10)
