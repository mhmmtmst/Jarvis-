import os
from pathlib import Path

_SKIP_DIRS = {
    "node_modules",
    "venv",
    ".venv",
    ".git",
    "__pycache__",
    "dist",
    "build",
    "agent-dist",
    "$RECYCLE.BIN",
    "System Volume Information",
}
_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".json",
    ".csv",
    ".log",
    ".html",
    ".css",
    ".yml",
    ".yaml",
    ".cfg",
    ".ini",
    ".xml",
    ".bat",
    ".ps1",
    ".sh",
}
_MAX_FILES_SCANNED = 5000
_MAX_RESULTS = 20
_CONTENT_READ_LIMIT = 200_000


def search_files(query: str, root: str = "", default_root: str = "") -> dict:
    """`root` altında (verilmezse `default_root`, o da boşsa kullanıcının home
    dizini) dosya adında veya metin içeriğinde `query`'yi (büyük/küçük harf
    duyarsız) arar. Sadece metin-benzeri uzantılı dosyaların içeriğine bakar;
    node_modules/venv/.git gibi gürültülü klasörleri ve gizli klasörleri atlar."""
    query_lower = query.strip().lower()
    if not query_lower:
        return {"status": "error", "message": "Aranacak bir kelime/ifade verilmedi."}

    base_path = root.strip() or default_root.strip() or str(Path.home())
    base = Path(base_path)
    if not base.exists():
        return {"status": "error", "message": f"Klasör bulunamadı: {base}"}

    matches: list[str] = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if scanned >= _MAX_FILES_SCANNED or len(matches) >= _MAX_RESULTS:
                break
            scanned += 1
            path = Path(dirpath) / name
            if query_lower in name.lower():
                matches.append(str(path))
                continue
            if path.suffix.lower() in _TEXT_EXTENSIONS:
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                        content = handle.read(_CONTENT_READ_LIMIT)
                except OSError:
                    continue
                if query_lower in content.lower():
                    matches.append(str(path))
        if scanned >= _MAX_FILES_SCANNED or len(matches) >= _MAX_RESULTS:
            break

    if not matches:
        return {"status": "ok", "message": "Eşleşen dosya bulunamadı.", "results": []}
    return {"status": "ok", "message": f"{len(matches)} dosya bulundu.", "results": matches}
