import difflib
import os
from pathlib import Path

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


def _default_shortcut_dirs() -> list[Path]:
    dirs = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        dirs.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        dirs.append(Path(userprofile) / "Desktop")
    public = os.environ.get("PUBLIC")
    if public:
        dirs.append(Path(public) / "Desktop")
    return dirs


_FUZZY_MATCH_CUTOFF = 0.72


def find_shortcut(isim: str, start_menu_dirs: list[Path] | None = None) -> str | None:
    """Kullanıcı/ortak Başlat Menüsü ve masaüstü klasörlerinde isme göre bir .lnk
    kısayolu arar (alt klasörler dahil, büyük/küçük harf duyarsız). Sırasıyla tam
    eşleşme, alt-dize eşleşmesi, sonra (ör. sesli komutun yanlış çözümlenmesi gibi
    ufak yazım farklarını yakalamak için) bulanık eşleşme dener."""
    target = isim.strip().lower()
    dirs = start_menu_dirs if start_menu_dirs is not None else _default_shortcut_dirs()

    candidates = []
    for base in dirs:
        base = Path(base)
        if not base.exists():
            continue
        candidates.extend(base.rglob("*.lnk"))

    for lnk in candidates:
        if lnk.stem.lower() == target:
            return str(lnk)
    for lnk in candidates:
        if target in lnk.stem.lower():
            return str(lnk)

    stems = [lnk.stem.lower() for lnk in candidates]
    close = difflib.get_close_matches(target, stems, n=1, cutoff=_FUZZY_MATCH_CUTOFF)
    if close:
        for lnk in candidates:
            if lnk.stem.lower() == close[0]:
                return str(lnk)
    return None


def open_app(isim: str, launcher=None, shortcut_finder=None) -> dict:
    """Open an application or file by (Turkish-friendly) name. `launcher`
    defaults to os.startfile but is injectable for testing. Bilinen olmayan
    isimler önce doğrudan denenir, başarısız olursa Başlat Menüsü kısayolu
    aranır (örn. Spotify, Discord gibi App Paths'te olmayan uygulamalar)."""
    if launcher is None:
        launcher = os.startfile
    if shortcut_finder is None:
        shortcut_finder = find_shortcut

    resolved = resolve_app_name(isim)
    try:
        launcher(resolved)
        return {"status": "ok", "message": f"{isim} açıldı."}
    except OSError:
        pass

    shortcut = shortcut_finder(isim)
    if shortcut:
        try:
            launcher(shortcut)
            return {"status": "ok", "message": f"{isim} açıldı."}
        except OSError as error:
            return {"status": "error", "message": f"{isim} açılamadı: {error}"}

    return {"status": "error", "message": f"{isim} açılamadı: uygulama bulunamadı."}
