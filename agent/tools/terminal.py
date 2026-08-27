import re
import subprocess

_DANGEROUS_PATTERNS = [
    r"\bformat\s+[a-z]:",
    r"\bformat-volume\b",
    r"\bclear-disk\b",
    r"\bdiskpart\b",
    r"\bshutdown\b",
    r"\bstop-computer\b",
    r"\brestart-computer\b",
    r"\brm\s+(-rf|-fr)\b",
    r"\brm\s+-r\s+-f\b",
    r"\brm\s+-f\s+-r\b",
    r"(?=.*\b(del|erase|rd)\b)(?=.*/s\b)(?=.*/q\b)",
    r"(?=.*\bremove-item\b)(?=.*-recurse\b)(?=.*-force\b)",
    r"\bvssadmin\s+delete\b",
    r"\breg\s+delete\b",
    r"\bnet\s+user\b.*\bdelete\b",
    r"-encodedcommand\b",
]


_RISKY_PATTERNS = [
    r"\b(del|erase)\b",
    r"\bremove-item\b",
    r"\btaskkill\b",
    r"\bstop-process\b",
    r"\bstop-service\b",
    r"\bnet\s+stop\b",
]


def is_dangerous(command: str) -> bool:
    lowered = command.lower()
    return any(re.search(pattern, lowered) for pattern in _DANGEROUS_PATTERNS)


def is_risky(command: str) -> bool:
    """Tamamen engellenmeyen ama önemli sonuç doğurabilecek (dosya silme,
    süreç/servis durdurma) komutlar — çalıştırılmadan önce onay ister.
    Zaten is_dangerous ile hard-block'lanan komutlar bu katmana ayrıca
    girmez (örn. -Recurse -Force zaten dangerous)."""
    if is_dangerous(command):
        return False
    lowered = command.lower()
    return any(re.search(pattern, lowered) for pattern in _RISKY_PATTERNS)


def run_command(command: str, cwd: str | None = None, runner=None, confirmed: bool = False) -> dict:
    """PowerShell üzerinden komut çalıştırır. `runner` testte enjekte
    edilir; gerçekte parametresiz bir closure olarak subprocess.run'ı
    komut/cwd'yi kapsayarak çağırır."""
    if is_dangerous(command):
        return {"status": "blocked", "message": "Bu komut güvenlik nedeniyle engellendi."}

    if is_risky(command) and not confirmed:
        return {
            "status": "needs_confirmation",
            "message": (
                f"'{command}' potansiyel olarak riskli bir komut (dosya/süreç/servis "
                "durduruyor veya siliyor). Kullanıcıdan sözlü onay al, onaylarsa AYNI "
                "komutu confirmed=true ile tekrar çağır."
            ),
        }

    if runner is None:
        def runner():
            return subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f"[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; {command}",
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

    try:
        result = runner()
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Komut zaman aşımına uğradı (30sn)."}
    except Exception as error:
        return {"status": "error", "message": f"Komut çalıştırılamadı: {error}"}

    stdout = (result.stdout or "")[:2000]
    stderr = (result.stderr or "")[:2000]
    output = stdout + stderr
    status = "ok" if result.returncode == 0 else "error"
    return {"status": status, "output": output, "returncode": result.returncode}
