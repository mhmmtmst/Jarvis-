import subprocess


def parse_report_projects(raw: str) -> list[tuple[str, str]]:
    """`.env`'deki JARVIS_REPORT_PROJECTS değerini (İsim:yol,İsim:yol,...)
    ayrıştırır. Windows path'leri sürücü harfinden sonra kendi `:`'sini
    içerdiği için her çift SADECE ilk `:` üzerinden bölünür."""
    projects = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        name, path = entry.split(":", 1)
        name = name.strip()
        path = path.strip()
        if name and path:
            projects.append((name, path))
    return projects


def get_projects_report(projects: list[tuple[str, str]], runner=None) -> dict:
    """Bilinen proje klasörlerinin git durumunu (branch, değişen dosya
    sayısı, son commit) toplar. Aynı git deposunun (toplevel) altındaki
    projeler tek bir repo grubunda toplanır, böylece paylaşılan bir depoda
    (örn. Odakla/jarvis/doğum-günü-sitesi aynı home-dir reposu) branch
    bilgisi tekrar tekrar sorulmaz. Bir projenin git komutları başarısız
    olursa veya beklenmeyen bir hata fırlatırsa, o proje `errors` listesine
    eklenir; diğer projeler işlenmeye devam eder."""
    if runner is None:
        def runner(args):
            return subprocess.run(
                args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
            )

    if not projects:
        return {"status": "error", "message": "Hiç proje yapılandırılmamış (JARVIS_REPORT_PROJECTS boş)."}

    repos: dict[str, dict] = {}
    order: list[str] = []
    errors: list[dict] = []

    for name, path in projects:
        try:
            toplevel_result = runner(["git", "-C", path, "rev-parse", "--show-toplevel"])
            if toplevel_result.returncode != 0:
                errors.append({"name": name, "message": "Git deposu bulunamadı."})
                continue

            toplevel = toplevel_result.stdout.strip()
            if toplevel not in repos:
                branch_result = runner(["git", "-C", toplevel, "branch", "--show-current"])
                branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
                branch = branch or "bilinmiyor"
                repos[toplevel] = {"toplevel": toplevel, "branch": branch, "projects": []}
                order.append(toplevel)

            status_result = runner(["git", "-C", toplevel, "status", "--porcelain", "--", path])
            changed_files = len(status_result.stdout.splitlines()) if status_result.returncode == 0 else 0

            log_result = runner(["git", "-C", toplevel, "log", "-1", "--format=%s|%ar", "--", path])
            last_commit = None
            if log_result.returncode == 0 and log_result.stdout.strip():
                message, _, relative_date = log_result.stdout.strip().partition("|")
                last_commit = {"message": message, "relative_date": relative_date}

            repos[toplevel]["projects"].append(
                {"name": name, "changed_files": changed_files, "last_commit": last_commit}
            )
        except Exception as error:
            errors.append({"name": name, "message": f"Rapor alınamadı: {error}"})

    return {
        "status": "ok",
        "repos": [repos[key] for key in order],
        "errors": errors,
    }
