import pytest
import requests

import firms_collector


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")


class _FakeSession:
    def __init__(self, response: _FakeResponse | None = None, exc: Exception | None = None):
        self._response = response
        self._exc = exc

    def get(self, url, timeout):
        if self._exc:
            raise self._exc
        return self._response


def test_days_outside_firms_limit_is_rejected_before_any_request(monkeypatch):
    with pytest.raises(ValueError, match="entre 1 e 5"):
        firms_collector.coletar("chave", "VIIRS_NOAA20_NRT", "-10,35,28,45", 10)


def test_days_zero_is_rejected():
    with pytest.raises(ValueError):
        firms_collector.coletar("chave", "VIIRS_NOAA20_NRT", "-10,35,28,45", 0)


def test_valid_csv_response_is_parsed(monkeypatch):
    csv_text = "latitude,longitude,acq_date,acq_time,confidence,frp\n38.5,23.0,2026-08-18,130,n,1.2\n"
    monkeypatch.setattr(firms_collector, "_sessao_resiliente", lambda: _FakeSession(_FakeResponse(csv_text)))
    df = firms_collector.coletar("chave", "VIIRS_NOAA20_NRT", "-10,35,28,45", 1)
    assert len(df) == 1
    assert df.iloc[0]["latitude"] == 38.5


def test_error_message_body_raises_clear_error_instead_of_silent_garbage(monkeypatch):
    # A FIRMS retorna HTTP 200 com uma linha de erro em texto puro quando a
    # MAP_KEY é inválida — não deve ser interpretado como CSV válido.
    monkeypatch.setattr(
        firms_collector, "_sessao_resiliente",
        lambda: _FakeSession(_FakeResponse("Invalid MAP_KEY")),
    )
    with pytest.raises(RuntimeError, match="não é um CSV válido"):
        firms_collector.coletar("chave-invalida", "VIIRS_NOAA20_NRT", "-10,35,28,45", 1)


def test_network_failure_raises_runtime_error(monkeypatch):
    monkeypatch.setattr(
        firms_collector, "_sessao_resiliente",
        lambda: _FakeSession(exc=requests.exceptions.Timeout("timed out")),
    )
    with pytest.raises(RuntimeError, match="Falha de rede"):
        firms_collector.coletar("chave", "VIIRS_NOAA20_NRT", "-10,35,28,45", 1)


def test_http_error_status_propagates(monkeypatch):
    monkeypatch.setattr(
        firms_collector, "_sessao_resiliente",
        lambda: _FakeSession(_FakeResponse("server error", status_code=500)),
    )
    with pytest.raises(requests.exceptions.HTTPError):
        firms_collector.coletar("chave", "VIIRS_NOAA20_NRT", "-10,35,28,45", 1)


def test_empty_but_valid_response_returns_empty_dataframe(monkeypatch):
    csv_text = "latitude,longitude,acq_date,acq_time,confidence,frp\n"
    monkeypatch.setattr(firms_collector, "_sessao_resiliente", lambda: _FakeSession(_FakeResponse(csv_text)))
    df = firms_collector.coletar("chave", "VIIRS_NOAA20_NRT", "-10,35,28,45", 1)
    assert df.empty
