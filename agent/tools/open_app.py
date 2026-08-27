import os

APP_ALIASES = {
    "not defteri": "notepad",
    "notepad": "notepad",
    "hesap makinesi": "calc",
    "calculator": "calc",
    "chrome": "chrome",
    "google chrome": "chrome",
    "explorer": "explorer",
    "dosya gezgini": "explorer",
}


def resolve_app_name(isim: str) -> str:
    key = isim.strip().lower()
    return APP_ALIASES.get(key, isim.strip())


def open_app(isim: str, launcher=None) -> dict:
    """Open an application or file by (Turkish-friendly) name. `launcher`
    defaults to os.startfile but is injectable for testing."""
    if launcher is None:
        launcher = os.startfile

    resolved = resolve_app_name(isim)
    try:
        launcher(resolved)
        return {"status": "ok", "message": f"{isim} açıldı."}
    except OSError as error:
        return {"status": "error", "message": f"{isim} açılamadı: {error}"}
