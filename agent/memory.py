import json
import os
import unicodedata
from datetime import datetime

_SOURCE_TREE_PATH = os.path.join(os.path.dirname(__file__), "memory.json")


def _default_path() -> str:
    """Paketlenmiş (kurulu) uygulamada Electron, `JARVIS_MEMORY_PATH`'i kullanıcının
    userData klasörüne işaret edecek şekilde ayarlar; böylece hafıza her
    auto-update'te silinip yeniden yazılan kurulum klasörü yerine kalıcı bir
    yerde durur. Env var yoksa (dev/test) kaynak ağacındaki eski konum kullanılır."""
    return os.environ.get("JARVIS_MEMORY_PATH") or _SOURCE_TREE_PATH


def _fold_turkish(text: str) -> str:
    text = text.lower().replace("ı", "i").replace("i̇", "i")
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def load_memory(path: str | None = None) -> dict:
    """Kategori -> {anahtar: {"value":..., "timestamp":...}} şeklinde ham
    hafıza. Dosya yoksa/bozuksa boş sözlük döner, hiçbir zaman hata fırlatmaz."""
    path = path or _default_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def remember(category: str = "notes", key: str = "", value: str = "", path: str | None = None) -> dict:
    """Bir bilgiyi kategori/anahtar altında kaydeder; aynı kategori+anahtar
    tekrar verilirse üzerine yazar (yığılan yinelenen kayıt yerine güncelleme)."""
    path = path or _default_path()
    category = (category or "notes").strip() or "notes"
    key = (key or "").strip()
    value = (value or "").strip()
    if not key or not value:
        return {"status": "error", "message": "Hafızaya yazılamadı: key ve value dolu olmalı."}

    data = load_memory(path)
    data.setdefault(category, {})[key] = {"value": value, "timestamp": datetime.now().isoformat()}
    _save(path, data)
    return {"status": "ok", "message": f"Hatırlayacağım: {key} = {value}"}


def recall(path: str | None = None) -> dict:
    data = load_memory(path or _default_path())
    items = [
        f"{category}/{key}: {entry.get('value', '')}"
        for category, entries in data.items()
        for key, entry in entries.items()
    ]
    if not items:
        return {"status": "ok", "items": [], "message": "Henüz hatırladığım bir şey yok."}
    return {"status": "ok", "items": items}


def delete_memory(category: str = "", key: str = "", match_text: str = "", path: str | None = None) -> dict:
    """category+key verilirse kesin, match_text verilirse (kategori/anahtar
    bilinmiyorsa) anahtar+değer içinde Türkçe-duyarsız bulanık arama yaparak siler."""
    path = path or _default_path()
    category = (category or "").strip()
    key = (key or "").strip()
    match_text = (match_text or "").strip()
    if not (category and key) and not match_text:
        return {"status": "error", "message": "Silmek için category+key veya match_text gerekli."}

    data = load_memory(path)
    deleted = []

    if category and key:
        if category in data and key in data[category]:
            del data[category][key]
            deleted.append(f"{category}/{key}")
    else:
        folded_match = _fold_turkish(match_text)
        for category_name in list(data.keys()):
            for key_name in list(data[category_name].keys()):
                entry = data[category_name][key_name]
                haystack = _fold_turkish(f"{key_name} {entry.get('value', '')}")
                if folded_match in haystack:
                    del data[category_name][key_name]
                    deleted.append(f"{category_name}/{key_name}")

    for category_name in list(data.keys()):
        if not data[category_name]:
            del data[category_name]

    if not deleted:
        return {"status": "ok", "message": "Eşleşen bir hafıza kaydı bulunamadı."}

    _save(path, data)
    return {"status": "ok", "message": f"Silindi: {', '.join(deleted)}"}


def format_memory_for_prompt(memory: dict) -> str:
    """Sistem promptuna eklenecek kompakt hafıza özeti. Boş hafızada boş
    string döner (promptu gereksiz yere şişirmemek için)."""
    if not memory:
        return ""
    lines = ["[HATIRLANAN BİLGİLER]"]
    for category, entries in memory.items():
        for key, entry in entries.items():
            lines.append(f"- {category}/{key}: {entry.get('value', '')}")
    return "\n".join(lines)
