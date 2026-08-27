import pytest

from agent.tools.open_app import open_app, resolve_app_name


def test_resolve_app_name_maps_known_turkish_alias():
    assert resolve_app_name("not defteri") == "notepad"


def test_resolve_app_name_is_case_and_space_insensitive():
    assert resolve_app_name("  Not Defteri  ") == "notepad"


def test_resolve_app_name_passes_through_unknown_names():
    assert resolve_app_name("spotify") == "spotify"


def test_open_app_calls_launcher_with_resolved_name_and_reports_success():
    calls = []

    def fake_launcher(name):
        calls.append(name)

    result = open_app("not defteri", launcher=fake_launcher)

    assert calls == ["notepad"]
    assert result == {"status": "ok", "message": "not defteri açıldı."}


def test_open_app_reports_error_when_launcher_fails():
    def failing_launcher(name):
        raise OSError("dosya bulunamadı")

    result = open_app("bilinmeyenuygulama", launcher=failing_launcher)

    assert result["status"] == "error"
    assert "bilinmeyenuygulama" in result["message"]
