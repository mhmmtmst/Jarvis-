from agent.tools.weather import get_weather_summary


class FakeResponse:
    def __init__(self, payload, status_ok=True):
        self._payload = payload
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise RuntimeError("HTTP hatası")

    def json(self):
        return self._payload


def make_payload(city="İstanbul", region="İstanbul", temp="21", desc="Az bulutlu", humidity="60", feels="20"):
    return {
        "nearest_area": [{"areaName": [{"value": city}], "region": [{"value": region}]}],
        "current_condition": [
            {
                "temp_C": temp,
                "FeelsLikeC": feels,
                "humidity": humidity,
                "weatherDesc": [{"value": desc}],
            }
        ],
    }


def test_get_weather_summary_uses_wttr_without_location_for_ip_autodetect():
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        return FakeResponse(make_payload())

    result = get_weather_summary(http_get=fake_get)

    assert calls[0][0] == "https://wttr.in/"
    assert result["status"] == "ok"
    assert result["city"] == "İstanbul"
    assert result["temp_c"] == "21"
    assert result["condition"] == "Az bulutlu"


def test_get_weather_summary_uses_explicit_location_in_url_and_label():
    def fake_get(url, params=None, timeout=None):
        return FakeResponse(make_payload(city="Samanpazarı", region="Ankara"))

    result = get_weather_summary(location="Ankara", http_get=fake_get)

    assert result["city"] == "Ankara"  # kullanicinin soyledigi kelime, tespit edilen mahalle degil
    assert "Ankara için hava durumu" in result["message"]


def test_get_weather_summary_uses_default_location_when_no_explicit_location():
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return FakeResponse(make_payload(city="Karabük", region="Karabük"))

    result = get_weather_summary(default_location="Safranbolu, Karabük", http_get=fake_get)

    assert calls[0] == "https://wttr.in/Safranbolu, Karabük"
    assert result["city"] == "Safranbolu, Karabük"


def test_get_weather_summary_explicit_location_overrides_default_location():
    def fake_get(url, params=None, timeout=None):
        return FakeResponse(make_payload())

    result = get_weather_summary(location="Ankara", default_location="Safranbolu, Karabük", http_get=fake_get)

    assert result["city"] == "Ankara"


def test_get_weather_summary_reports_error_on_request_failure():
    def failing_get(url, params=None, timeout=None):
        raise ConnectionError("ağ hatası")

    result = get_weather_summary(http_get=failing_get)

    assert result["status"] == "error"


def test_get_weather_summary_reports_error_on_bad_status():
    def fake_get(url, params=None, timeout=None):
        return FakeResponse(make_payload(), status_ok=False)

    result = get_weather_summary(http_get=fake_get)

    assert result["status"] == "error"


def test_get_weather_summary_reports_error_on_malformed_payload():
    def fake_get(url, params=None, timeout=None):
        return FakeResponse({"unexpected": "shape"})

    result = get_weather_summary(http_get=fake_get)

    assert result["status"] == "error"
