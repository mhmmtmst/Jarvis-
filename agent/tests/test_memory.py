import json
import os

from agent.memory import (
    _SOURCE_TREE_PATH,
    _default_path,
    delete_memory,
    format_memory_for_prompt,
    load_memory,
    recall,
    remember,
)


def test_recall_returns_empty_list_when_file_does_not_exist(tmp_path):
    path = str(tmp_path / "memory.json")

    result = recall(path=path)

    assert result == {"status": "ok", "items": [], "message": "Henüz hatırladığım bir şey yok."}


def test_remember_creates_file_with_category_key_value(tmp_path):
    path = str(tmp_path / "memory.json")

    result = remember(category="identity", key="kedi_adi", value="Pamuk", path=path)

    assert result == {"status": "ok", "message": "Hatırlayacağım: kedi_adi = Pamuk"}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["identity"]["kedi_adi"]["value"] == "Pamuk"
    assert "timestamp" in data["identity"]["kedi_adi"]


def test_remember_defaults_to_notes_category_when_not_given(tmp_path):
    path = str(tmp_path / "memory.json")

    remember(key="tercih", value="kahve seker", path=path)

    data = load_memory(path)
    assert data["notes"]["tercih"]["value"] == "kahve seker"


def test_remember_overwrites_same_category_and_key(tmp_path):
    path = str(tmp_path / "memory.json")
    remember(category="identity", key="isim", value="Mehmet", path=path)

    remember(category="identity", key="isim", value="Muhammet", path=path)

    data = load_memory(path)
    assert data["identity"]["isim"]["value"] == "Muhammet"
    assert len(data["identity"]) == 1


def test_remember_reports_error_when_key_or_value_missing(tmp_path):
    path = str(tmp_path / "memory.json")

    result = remember(category="notes", key="", value="bir şey", path=path)

    assert result["status"] == "error"
    assert load_memory(path) == {}


def test_recall_returns_all_remembered_entries_formatted(tmp_path):
    path = str(tmp_path / "memory.json")
    remember(category="identity", key="isim", value="Muhammet", path=path)
    remember(category="notes", key="tercih", value="kahve seker", path=path)

    result = recall(path=path)

    assert result["status"] == "ok"
    assert "identity/isim: Muhammet" in result["items"]
    assert "notes/tercih: kahve seker" in result["items"]


def test_recall_returns_empty_list_when_file_is_corrupt_json(tmp_path):
    path = str(tmp_path / "memory.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{bu gecerli json degil")

    result = recall(path=path)

    assert result == {"status": "ok", "items": [], "message": "Henüz hatırladığım bir şey yok."}


def test_remember_overwrites_corrupt_file_instead_of_raising(tmp_path):
    path = str(tmp_path / "memory.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("bozuk dosya {{{")

    result = remember(category="notes", key="deneme", value="yeni bilgi", path=path)

    assert result["status"] == "ok"
    data = load_memory(path)
    assert data == {"notes": {"deneme": {"value": "yeni bilgi", "timestamp": data["notes"]["deneme"]["timestamp"]}}}


def test_delete_memory_removes_exact_category_and_key(tmp_path):
    path = str(tmp_path / "memory.json")
    remember(category="identity", key="isim", value="Muhammet", path=path)

    result = delete_memory(category="identity", key="isim", path=path)

    assert result["status"] == "ok"
    assert load_memory(path) == {}


def test_delete_memory_fuzzy_matches_text_across_all_entries(tmp_path):
    path = str(tmp_path / "memory.json")
    remember(category="notes", key="Claude limiti", value="haftalık 40 saat", path=path)
    remember(category="identity", key="isim", value="Muhammet", path=path)

    result = delete_memory(match_text="claude limiti", path=path)

    assert result["status"] == "ok"
    data = load_memory(path)
    assert "notes" not in data
    assert data["identity"]["isim"]["value"] == "Muhammet"


def test_delete_memory_reports_no_match_without_raising(tmp_path):
    path = str(tmp_path / "memory.json")
    remember(category="notes", key="a", value="b", path=path)

    result = delete_memory(match_text="hiç alakasız bir şey", path=path)

    assert result["status"] == "ok"
    assert "bulunamadı" in result["message"]
    assert load_memory(path)["notes"]["a"]["value"] == "b"


def test_delete_memory_requires_category_key_pair_or_match_text():
    result = delete_memory(category="notes")

    assert result["status"] == "error"


def test_format_memory_for_prompt_returns_empty_string_for_empty_memory():
    assert format_memory_for_prompt({}) == ""


def test_format_memory_for_prompt_lists_all_categories_and_keys():
    memory = {
        "identity": {"isim": {"value": "Muhammet", "timestamp": "x"}},
        "notes": {"proje": {"value": "Odakla", "timestamp": "y"}},
    }

    text = format_memory_for_prompt(memory)

    assert "identity/isim: Muhammet" in text
    assert "notes/proje: Odakla" in text
    assert text.startswith("[HATIRLANAN BİLGİLER]")


def test_remember_and_recall_use_jarvis_memory_path_env_var_when_no_path_given(tmp_path, monkeypatch):
    custom_path = str(tmp_path / "custom_memory.json")
    monkeypatch.setenv("JARVIS_MEMORY_PATH", custom_path)

    remember(category="identity", key="isim", value="Muhammet")

    assert os.path.exists(custom_path)
    assert recall()["items"] == ["identity/isim: Muhammet"]


def test_default_path_falls_back_to_source_tree_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("JARVIS_MEMORY_PATH", raising=False)

    assert _default_path() == _SOURCE_TREE_PATH
