"""Limitador de transações em janela deslizante para a FIRMS (RNF02: 5000 / 10 min).

O custo de uma requisição na FIRMS não é fixo (medido em 2026-10-21: uma consulta de 2 dias do
VIIRS sobre o Mediterrâneo consumiu 4 transações). Por isso o limitador trabalha com custo
estimado e é ressincronizado com o contador oficial (`/mapserver/mapkey_status/`) a cada ciclo.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable

logger = logging.getLogger("ignis.collector")

FIRMS_TRANSACTION_LIMIT = 5000
FIRMS_WINDOW_SECONDS = 600


class RateLimitExceeded(RuntimeError):
    pass


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int = FIRMS_TRANSACTION_LIMIT,
        window_seconds: float = FIRMS_WINDOW_SECONDS,
        safety_ratio: float = 0.9,
        max_wait_seconds: float = FIRMS_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        # margem de segurança: outros clientes (ex.: smoke test) podem usar a mesma chave
        self.budget = int(limit * safety_ratio)
        self.window = window_seconds
        self.max_wait = max_wait_seconds
        self._clock = clock
        self._sleep = sleep
        self._events: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= self.window:
            self._events.popleft()

    def used(self) -> int:
        with self._lock:
            self._prune(self._clock())
            return sum(cost for _, cost in self._events)

    def acquire(self, cost: int = 1) -> float:
        """Reserva `cost` transações, esperando a janela liberar se preciso. Retorna o tempo esperado."""
        if cost > self.budget:
            raise RateLimitExceeded(f"custo {cost} maior que o orçamento da janela ({self.budget})")
        waited = 0.0
        while True:
            with self._lock:
                now = self._clock()
                self._prune(now)
                used = sum(c for _, c in self._events)
                if used + cost <= self.budget:
                    self._events.append((now, cost))
                    return waited
                # espera até o evento mais antigo sair da janela
                wait = self.window - (now - self._events[0][0])
            if waited + wait > self.max_wait:
                raise RateLimitExceeded(
                    f"orçamento da janela esgotado ({used}/{self.budget}); tente no próximo ciclo"
                )
            logger.info("Limite da FIRMS próximo (%d/%d): aguardando %.0fs", used, self.budget, wait)
            self._sleep(wait)
            waited += wait

    def sync(self, current_transactions: int) -> None:
        """Ajusta o contador local ao valor oficial, quando a FIRMS informa uso maior que o nosso."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            local = sum(c for _, c in self._events)
            if current_transactions > local:
                self._events.append((now, current_transactions - local))
