import subprocess
from types import SimpleNamespace

from agent.tools.terminal import is_dangerous, run_command


def test_is_dangerous_detects_format_command():
    assert is_dangerous("format C:") is True


def test_is_dangerous_detects_diskpart():
    assert is_dangerous("diskpart") is True


def test_is_dangerous_detects_shutdown():
    assert is_dangerous("shutdown /s /t 0") is True


def test_is_dangerous_detects_rm_rf_root():
    assert is_dangerous("rm -rf /") is True


def test_is_dangerous_detects_root_delete_variants():
    assert is_dangerous("del /s /q C:\\") is True
    assert is_dangerous("rd /s /q D:\\") is True
    assert is_dangerous("Remove-Item -Recurse -Force C:\\") is True


def test_is_dangerous_allows_safe_commands():
    assert is_dangerous("git status") is False
    assert is_dangerous("npm test") is False
    assert is_dangerous("dir") is False
    assert is_dangerous("python -m pytest") is False


def test_is_dangerous_detects_del_with_swapped_flag_order():
    assert is_dangerous("del /q /s C:\\") is True


def test_is_dangerous_detects_rd_on_real_subdirectory():
    assert is_dangerous("rd /s /q C:\\Windows") is True


def test_is_dangerous_detects_remove_item_on_real_subdirectory():
    assert is_dangerous("Remove-Item -Recurse -Force C:\\Users\\mhmmt") is True


def test_is_dangerous_detects_remove_item_with_env_var_target():
    assert is_dangerous("Remove-Item -Recurse -Force $env:USERPROFILE") is True


def test_is_dangerous_detects_remove_item_piped_from_get_childitem():
    assert is_dangerous("Get-ChildItem C:\\ -Recurse | Remove-Item -Force") is True


def test_is_dangerous_detects_rm_with_separate_flags():
    assert is_dangerous("rm -r -f /") is True


def test_is_dangerous_detects_format_volume():
    assert is_dangerous("Format-Volume -DriveLetter C") is True


def test_is_dangerous_detects_clear_disk():
    assert is_dangerous("Clear-Disk -Number 0 -RemoveData") is True


def test_is_dangerous_detects_encodedcommand_obfuscation():
    assert is_dangerous("powershell -EncodedCommand aQBlAHgA") is True


def test_run_command_blocks_dangerous_without_calling_runner():
    calls = []
    def runner():
        calls.append(1)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    result = run_command("format C:", runner=runner)

    assert result["status"] == "blocked"
    assert calls == []


def test_run_command_returns_ok_on_success():
    def runner():
        return SimpleNamespace(stdout="merhaba\n", stderr="", returncode=0)

    result = run_command("echo merhaba", runner=runner)

    assert result["status"] == "ok"
    assert "merhaba" in result["output"]
    assert result["returncode"] == 0


def test_run_command_returns_error_on_nonzero_exit():
    def runner():
        return SimpleNamespace(stdout="", stderr="komut bulunamadı", returncode=1)

    result = run_command("not-a-real-command", runner=runner)

    assert result["status"] == "error"
    assert result["returncode"] == 1


def test_run_command_truncates_long_output():
    def runner():
        return SimpleNamespace(stdout="x" * 5000, stderr="", returncode=0)

    result = run_command("dir", runner=runner)

    assert len(result["output"]) <= 2000


def test_run_command_preserves_stderr_when_stdout_is_long():
    def runner():
        return SimpleNamespace(stdout="x" * 5000, stderr="ONEMLI HATA MESAJI", returncode=1)

    result = run_command("dir", runner=runner)

    assert "ONEMLI HATA MESAJI" in result["output"]


def test_run_command_handles_timeout():
    def runner():
        raise subprocess.TimeoutExpired(cmd="sleep 100", timeout=30)

    result = run_command("sleep 100", runner=runner)

    assert result["status"] == "error"
    assert "zaman aşımı" in result["message"]


def test_run_command_handles_invalid_cwd():
    def runner():
        raise FileNotFoundError("klasör yok")

    result = run_command("dir", cwd="C:\\olmayan\\klasor", runner=runner)

    assert result["status"] == "error"


def test_run_command_handles_unexpected_runner_exception():
    def runner():
        raise TypeError("beklenmedik hata")

    result = run_command("dir", runner=runner)

    assert result["status"] == "error"


def test_run_command_handles_turkish_characters_via_real_subprocess():
    """Regression test for the encoding crash: PowerShell output containing
    ordinary Turkish characters must not raise, using the real (non-injected)
    subprocess.run path."""
    result = run_command('Write-Output "Ş ü Ğ İ ı"')

    assert result["status"] == "ok"
    assert result["output"] != ""
