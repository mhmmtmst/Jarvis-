from agent.tools.files import search_files


def test_search_files_matches_filename_case_insensitive(tmp_path):
    (tmp_path / "Toplanti_Notlari.txt").write_text("alakasız içerik", encoding="utf-8")
    (tmp_path / "diger.txt").write_text("alakasız içerik", encoding="utf-8")

    result = search_files("toplanti", root=str(tmp_path))

    assert result["status"] == "ok"
    assert any("Toplanti_Notlari.txt" in path for path in result["results"])
    assert not any("diger.txt" in path for path in result["results"])


def test_search_files_matches_file_content_case_insensitive(tmp_path):
    (tmp_path / "not.txt").write_text("Bu dosyada ANAHTAR KELIME geçiyor.", encoding="utf-8")
    (tmp_path / "baska.txt").write_text("bununla ilgisi yok", encoding="utf-8")

    result = search_files("anahtar kelime", root=str(tmp_path))

    assert any("not.txt" in path for path in result["results"])
    assert not any("baska.txt" in path for path in result["results"])


def test_search_files_searches_subfolders(tmp_path):
    sub = tmp_path / "alt_klasor"
    sub.mkdir()
    (sub / "rapor.md").write_text("bulunması gereken metin burada", encoding="utf-8")

    result = search_files("bulunması gereken", root=str(tmp_path))

    assert any("rapor.md" in path for path in result["results"])


def test_search_files_skips_noisy_directories(tmp_path):
    noisy = tmp_path / "node_modules"
    noisy.mkdir()
    (noisy / "eşleşen.txt").write_text("hedef kelime burada", encoding="utf-8")

    result = search_files("hedef kelime", root=str(tmp_path))

    assert result["results"] == []


def test_search_files_ignores_non_text_extensions_for_content_match(tmp_path):
    # .exe içine metin gömülü olsa bile içerik taraması yapılmamalı (ikili
    # dosyaları okumak hem yavaş hem anlamsız); dosya adı eşleşmesi hâlâ çalışır.
    binary_like = tmp_path / "program.exe"
    binary_like.write_bytes(b"HEDEF KELIME ama bu bir exe")

    result = search_files("hedef kelime", root=str(tmp_path))

    assert result["results"] == []


def test_search_files_returns_ok_with_empty_results_when_nothing_matches(tmp_path):
    (tmp_path / "a.txt").write_text("bir şey", encoding="utf-8")

    result = search_files("bulunamayacak-bir-ifade", root=str(tmp_path))

    assert result["status"] == "ok"
    assert result["results"] == []


def test_search_files_errors_on_empty_query(tmp_path):
    result = search_files("   ", root=str(tmp_path))

    assert result["status"] == "error"


def test_search_files_errors_when_root_does_not_exist():
    result = search_files("bir şey", root="C:/bu-klasor-hic-olmayacak-xyz")

    assert result["status"] == "error"


def test_search_files_falls_back_to_default_root_when_root_not_given(tmp_path):
    (tmp_path / "hedef.txt").write_text("içerik", encoding="utf-8")

    result = search_files("hedef", root="", default_root=str(tmp_path))

    assert any("hedef.txt" in path for path in result["results"])
