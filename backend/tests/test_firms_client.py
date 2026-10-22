from datetime import date

import responses

from ignis.collectors.firms import client

MODIS_CSV = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,"
    "version,bright_t31,frp,daynight\n"
    "37.9,23.7,320.5,1.0,1.0,2026-10-20,1050,Terra,MODIS,85,6.1NRT,290.1,12.3,D\n"
)


@responses.activate
def test_window_with_start_date_is_appended_to_url():
    url = f"{client.FIRMS_BASE_URL}/k/VIIRS_SNPP_NRT/-10,35,28,45/5/2026-09-01"
    responses.get(url, body="latitude,longitude,acq_date,acq_time\n")

    df = client.coletar("k", "VIIRS_SNPP_NRT", "-10,35,28,45", 5, date(2026, 9, 1))

    assert df.empty
    assert responses.calls[0].request.url == url


@responses.activate
def test_modis_brightness_column_is_kept():
    responses.get(f"{client.FIRMS_BASE_URL}/k/MODIS_NRT/-10,35,28,45/1", body=MODIS_CSV)

    df = client.coletar("k", "MODIS_NRT", "-10,35,28,45", 1)

    assert "brightness" in df.columns
    assert "bright_t31" not in df.columns  # colunas fora do interesse são descartadas


@responses.activate
def test_key_status_is_parsed():
    responses.get(
        client.FIRMS_STATUS_URL,
        json={"transaction_limit": 5000, "current_transactions": 4, "transaction_interval": "10 minutes"},
    )

    assert client.consultar_status("k") == {"transaction_limit": 5000, "current_transactions": 4}
    assert "MAP_KEY=k" in responses.calls[0].request.url


@responses.activate
def test_key_status_unavailable_returns_none_instead_of_failing_the_cycle():
    responses.get(client.FIRMS_STATUS_URL, body="Invalid MAP_KEY.")
    assert client.consultar_status("k") is None
