import urllib.parse
import webbrowser

from agent.tools.browser import open_browser, play_media, resolve_target_url


def test_resolve_target_url_passes_through_full_url():
    assert resolve_target_url("https://example.com") == "https://example.com"


def test_resolve_target_url_adds_scheme_to_bare_domain():
    assert resolve_target_url("python.org") == "https://python.org"


def test_resolve_target_url_adds_scheme_to_domain_with_path():
    assert resolve_target_url("github.com/anthropics") == "https://github.com/anthropics"


def test_resolve_target_url_treats_phrase_as_search_query():
    query = "İstanbul hava durumu"
    expected = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    assert resolve_target_url(query) == expected


def test_resolve_target_url_treats_multi_word_phrase_without_dot_as_search():
    query = "python nedir"
    expected = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    assert resolve_target_url(query) == expected


def test_resolve_target_url_treats_non_http_scheme_as_search_query():
    query = "ftp://example.com"
    expected = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    assert resolve_target_url(query) == expected


def test_open_browser_calls_opener_with_resolved_url_and_returns_ok():
    calls = []
    def opener(url):
        calls.append(url)
        return True

    result = open_browser("python.org", opener=opener)

    assert calls == ["https://python.org"]
    assert result["status"] == "ok"


def test_open_browser_returns_error_when_opener_fails():
    result = open_browser("python.org", opener=lambda url: False)

    assert result["status"] == "error"


def test_open_browser_returns_error_when_opener_raises():
    def opener(url):
        raise webbrowser.Error("could not locate runnable browser")

    result = open_browser("python.org", opener=opener)

    assert result["status"] == "error"


def test_play_media_defaults_to_youtube_search():
    calls = []
    def opener(url):
        calls.append(url)
        return True

    result = play_media("bohemian rhapsody", opener=opener)

    assert calls == ["https://www.youtube.com/results?search_query=bohemian%20rhapsody"]
    assert result["status"] == "ok"


def test_play_media_uses_spotify_when_requested():
    calls = []
    def opener(url):
        calls.append(url)
        return True

    play_media("bohemian rhapsody", platform="spotify", opener=opener)

    assert calls == ["https://open.spotify.com/search/bohemian%20rhapsody"]


def test_play_media_returns_error_when_opener_fails():
    result = play_media("test", opener=lambda url: False)

    assert result["status"] == "error"


def test_play_media_returns_error_when_opener_raises():
    def opener(url):
        raise webbrowser.Error("could not locate runnable browser")

    result = play_media("test", opener=opener)

    assert result["status"] == "error"
