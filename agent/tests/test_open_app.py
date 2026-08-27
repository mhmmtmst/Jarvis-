import pytest

from agent.tools.open_app import (
    _default_shortcut_dirs,
    find_shortcut,
    open_app,
    resolve_app_name,
)


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


def test_open_app_reports_error_when_launcher_fails_and_no_shortcut_found():
    def failing_launcher(name):
        raise OSError("dosya bulunamadı")

    result = open_app(
        "bilinmeyenuygulama", launcher=failing_launcher, shortcut_finder=lambda isim: None
    )

    assert result["status"] == "error"
    assert "bilinmeyenuygulama" in result["message"]


def test_find_shortcut_matches_lnk_by_exact_stem_case_insensitive(tmp_path):
    programs = tmp_path / "Programs"
    programs.mkdir()
    (programs / "Spotify.lnk").write_text("")
    (programs / "Discord.lnk").write_text("")

    result = find_shortcut("spotify", start_menu_dirs=[programs])

    assert result == str(programs / "Spotify.lnk")


def test_find_shortcut_searches_subfolders(tmp_path):
    sub = tmp_path / "Programs" / "Accessibility"
    sub.mkdir(parents=True)
    (sub / "Magnify.lnk").write_text("")

    result = find_shortcut("magnify", start_menu_dirs=[tmp_path / "Programs"])

    assert result == str(sub / "Magnify.lnk")


def test_find_shortcut_returns_none_when_nothing_matches(tmp_path):
    programs = tmp_path / "Programs"
    programs.mkdir()
    (programs / "Discord.lnk").write_text("")

    result = find_shortcut("spotify", start_menu_dirs=[programs])

    assert result is None


def test_open_app_falls_back_to_start_menu_shortcut_when_bare_name_fails():
    calls = []

    def launcher(name):
        calls.append(name)
        if name == "spotify":
            raise OSError("Sistem belirtilen dosyayı bulamıyor")

    result = open_app(
        "spotify",
        launcher=launcher,
        shortcut_finder=lambda isim: r"C:\Users\x\Spotify.lnk",
    )

    assert calls == ["spotify", r"C:\Users\x\Spotify.lnk"]
    assert result == {"status": "ok", "message": "spotify açıldı."}


def test_open_app_reports_not_found_when_shortcut_also_missing():
    def failing_launcher(name):
        raise OSError("bulunamadı")

    result = open_app("hicbiryerdeolmayanuygulama", launcher=failing_launcher, shortcut_finder=lambda isim: None)

    assert result["status"] == "error"
    assert "hicbiryerdeolmayanuygulama" in result["message"]


def test_find_shortcut_falls_back_to_fuzzy_match_for_near_miss_typos(tmp_path):
    programs = tmp_path / "Programs"
    programs.mkdir()
    (programs / "Spotify.lnk").write_text("")

    # Gemini'nin sesli komutu yanlış çözümlemesi gibi ufak bir yazım farkı
    result = find_shortcut("spotifay", start_menu_dirs=[programs])

    assert result == str(programs / "Spotify.lnk")


def test_find_shortcut_fuzzy_match_does_not_fire_for_unrelated_names(tmp_path):
    programs = tmp_path / "Programs"
    programs.mkdir()
    (programs / "Discord.lnk").write_text("")

    result = find_shortcut("spotify", start_menu_dirs=[programs])

    assert result is None


def test_default_shortcut_dirs_includes_start_menu_and_desktop(monkeypatch):
    monkeypatch.setenv("APPDATA", r"C:\Users\x\AppData\Roaming")
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
    monkeypatch.setenv("USERPROFILE", r"C:\Users\x")
    monkeypatch.setenv("PUBLIC", r"C:\Users\Public")

    dirs = {str(p) for p in _default_shortcut_dirs()}

    assert str(r"C:\Users\x\AppData\Roaming\Microsoft\Windows\Start Menu\Programs") in dirs
    assert str(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs") in dirs
    assert str(r"C:\Users\x\Desktop") in dirs
    assert str(r"C:\Users\Public\Desktop") in dirs
