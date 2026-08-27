import re
import urllib.parse
import webbrowser

_DOMAIN_LIKE = re.compile(r"^[\w-]+(\.[\w-]+)+(/\S*)?$")


def resolve_target_url(query_or_url: str) -> str:
    """http(s):// ile başlayan ya da 'domain.tld' gibi görünen (boşluksuz)
    girdiyi olduğu gibi (şema eksikse https:// eklenerek) döner; aksi halde
    Google arama URL'i olarak döner."""
    text = query_or_url.strip()
    if text.startswith(("http://", "https://")):
        return text
    if " " not in text and _DOMAIN_LIKE.match(text):
        return f"https://{text}"
    return f"https://www.google.com/search?q={urllib.parse.quote(text)}"


def open_browser(query_or_url: str, opener=None) -> dict:
    if opener is None:
        opener = webbrowser.open
    url = resolve_target_url(query_or_url)
    try:
        opened = opener(url)
    except Exception as error:
        return {"status": "error", "message": f"Tarayıcı açılamadı: {error}"}
    if opened:
        return {"status": "ok", "message": f"Tarayıcıda açıldı: {url}"}
    return {"status": "error", "message": f"Tarayıcı açılamadı: {url}"}


def play_media(query: str, platform: str = "youtube", opener=None) -> dict:
    if opener is None:
        opener = webbrowser.open
    if platform == "spotify":
        url = f"https://open.spotify.com/search/{urllib.parse.quote(query)}"
    else:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
    try:
        opened = opener(url)
    except Exception as error:
        return {"status": "error", "message": f"Tarayıcı açılamadı: {error}"}
    if opened:
        return {"status": "ok", "message": f"Tarayıcıda açıldı: {url}"}
    return {"status": "error", "message": f"Tarayıcı açılamadı: {url}"}
