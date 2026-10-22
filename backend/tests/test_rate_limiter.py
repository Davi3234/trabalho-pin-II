import pytest

from ignis.collectors.firms.rate_limiter import RateLimitExceeded, SlidingWindowRateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _limiter(clock: FakeClock, limit=100, window=600, **kw) -> SlidingWindowRateLimiter:
    return SlidingWindowRateLimiter(
        limit=limit, window_seconds=window, safety_ratio=1.0, clock=clock, sleep=clock.sleep, **kw
    )


def test_acquire_within_budget_does_not_wait():
    clock = FakeClock()
    limiter = _limiter(clock)
    for _ in range(10):
        assert limiter.acquire(10) == 0
    assert limiter.used() == 100
    assert clock.sleeps == []


def test_acquire_over_budget_waits_for_oldest_event_to_leave_window():
    clock = FakeClock()
    limiter = _limiter(clock)
    limiter.acquire(60)
    clock.now = 100
    limiter.acquire(40)
    clock.now = 200

    waited = limiter.acquire(10)  # precisa que o evento de t=0 saia da janela (t=600)

    assert waited == pytest.approx(400)
    assert limiter.used() == 50  # 40 (t=100) + 10 (t=600)


def test_window_slides_and_frees_budget():
    clock = FakeClock()
    limiter = _limiter(clock)
    limiter.acquire(100)
    clock.now = 600
    assert limiter.used() == 0


def test_safety_ratio_reserves_part_of_the_official_limit():
    limiter = SlidingWindowRateLimiter(limit=5000, safety_ratio=0.9)
    assert limiter.budget == 4500


def test_cost_larger_than_budget_is_rejected_immediately():
    clock = FakeClock()
    with pytest.raises(RateLimitExceeded):
        _limiter(clock).acquire(101)


def test_gives_up_instead_of_waiting_longer_than_max_wait():
    clock = FakeClock()
    limiter = _limiter(clock, max_wait_seconds=60)
    limiter.acquire(100)
    with pytest.raises(RateLimitExceeded, match="próximo ciclo"):
        limiter.acquire(1)
    assert clock.sleeps == []


def test_sync_with_official_counter_accounts_for_other_clients():
    clock = FakeClock()
    limiter = _limiter(clock)
    limiter.acquire(10)
    limiter.sync(current_transactions=70)  # a FIRMS viu 60 transações a mais (outro cliente)
    assert limiter.used() == 70
    limiter.sync(current_transactions=20)  # valor menor que o local não reduz a contagem
    assert limiter.used() == 70
