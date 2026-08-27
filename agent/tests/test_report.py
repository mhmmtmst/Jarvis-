from types import SimpleNamespace

from agent.tools.report import get_projects_report, parse_report_projects


def _result(returncode=0, stdout=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout)


def test_parse_report_projects_splits_name_and_windows_path():
    raw = "Odakla:C:/Users/mhmmt/OneDrive/Masaüstü/Odakla,Jarvis:C:/Users/mhmmt/OneDrive/Masaüstü/jarvis"

    projects = parse_report_projects(raw)

    assert projects == [
        ("Odakla", "C:/Users/mhmmt/OneDrive/Masaüstü/Odakla"),
        ("Jarvis", "C:/Users/mhmmt/OneDrive/Masaüstü/jarvis"),
    ]


def test_parse_report_projects_ignores_empty_and_malformed_entries():
    raw = "Odakla:C:/Odakla, , NoColonHere ,ChronoPlay:C:/chronoplay"

    projects = parse_report_projects(raw)

    assert projects == [
        ("Odakla", "C:/Odakla"),
        ("ChronoPlay", "C:/chronoplay"),
    ]


def test_parse_report_projects_returns_empty_list_for_empty_string():
    assert parse_report_projects("") == []


def test_get_projects_report_returns_error_when_no_projects_configured():
    result = get_projects_report(projects=[])

    assert result == {
        "status": "error",
        "message": "Hiç proje yapılandırılmamış (JARVIS_REPORT_PROJECTS boş).",
    }


def test_get_projects_report_groups_projects_sharing_same_toplevel():
    responses = {
        ("git", "-C", "C:/home/Odakla", "rev-parse", "--show-toplevel"): _result(stdout="C:/home\n"),
        ("git", "-C", "C:/home/Jarvis", "rev-parse", "--show-toplevel"): _result(stdout="C:/home\n"),
        ("git", "-C", "C:/home", "branch", "--show-current"): _result(stdout="master\n"),
        ("git", "-C", "C:/home", "status", "--porcelain", "--", "C:/home/Odakla"): _result(stdout=""),
        ("git", "-C", "C:/home", "log", "-1", "--format=%s|%ar", "--", "C:/home/Odakla"): _result(
            stdout="fix: x|2 gün önce"
        ),
        ("git", "-C", "C:/home", "status", "--porcelain", "--", "C:/home/Jarvis"): _result(
            stdout=" M a.py\n?? b.py\n"
        ),
        ("git", "-C", "C:/home", "log", "-1", "--format=%s|%ar", "--", "C:/home/Jarvis"): _result(
            stdout="feat: y|1 saat önce"
        ),
    }

    def runner(args):
        return responses[tuple(args)]

    result = get_projects_report(
        projects=[("Odakla", "C:/home/Odakla"), ("Jarvis", "C:/home/Jarvis")],
        runner=runner,
    )

    assert result["status"] == "ok"
    assert len(result["repos"]) == 1
    repo = result["repos"][0]
    assert repo["toplevel"] == "C:/home"
    assert repo["branch"] == "master"
    assert repo["projects"] == [
        {
            "name": "Odakla",
            "changed_files": 0,
            "last_commit": {"message": "fix: x", "relative_date": "2 gün önce"},
        },
        {
            "name": "Jarvis",
            "changed_files": 2,
            "last_commit": {"message": "feat: y", "relative_date": "1 saat önce"},
        },
    ]
    assert result["errors"] == []


def test_get_projects_report_falls_back_to_bilinmiyor_when_branch_is_detached():
    responses = {
        ("git", "-C", "C:/home/Odakla", "rev-parse", "--show-toplevel"): _result(stdout="C:/home\n"),
        ("git", "-C", "C:/home", "branch", "--show-current"): _result(returncode=0, stdout=""),
        ("git", "-C", "C:/home", "status", "--porcelain", "--", "C:/home/Odakla"): _result(stdout=""),
        ("git", "-C", "C:/home", "log", "-1", "--format=%s|%ar", "--", "C:/home/Odakla"): _result(
            stdout="fix: x|2 gün önce"
        ),
    }

    def runner(args):
        return responses[tuple(args)]

    result = get_projects_report(
        projects=[("Odakla", "C:/home/Odakla")],
        runner=runner,
    )

    assert result["repos"][0]["branch"] == "bilinmiyor"


def test_get_projects_report_treats_separate_repo_as_its_own_group():
    responses = {
        ("git", "-C", "C:/home/Odakla", "rev-parse", "--show-toplevel"): _result(stdout="C:/home\n"),
        ("git", "-C", "C:/chronoplay", "rev-parse", "--show-toplevel"): _result(stdout="C:/chronoplay\n"),
        ("git", "-C", "C:/home", "branch", "--show-current"): _result(stdout="master\n"),
        ("git", "-C", "C:/home", "status", "--porcelain", "--", "C:/home/Odakla"): _result(stdout=""),
        ("git", "-C", "C:/home", "log", "-1", "--format=%s|%ar", "--", "C:/home/Odakla"): _result(
            stdout="fix: x|2 gün önce"
        ),
        ("git", "-C", "C:/chronoplay", "branch", "--show-current"): _result(stdout="main\n"),
        ("git", "-C", "C:/chronoplay", "status", "--porcelain", "--", "C:/chronoplay"): _result(
            stdout=" M f.cs\n"
        ),
        ("git", "-C", "C:/chronoplay", "log", "-1", "--format=%s|%ar", "--", "C:/chronoplay"): _result(
            stdout="wip|3 gün önce"
        ),
    }

    def runner(args):
        return responses[tuple(args)]

    result = get_projects_report(
        projects=[("Odakla", "C:/home/Odakla"), ("ChronoPlay", "C:/chronoplay")],
        runner=runner,
    )

    assert [repo["toplevel"] for repo in result["repos"]] == ["C:/home", "C:/chronoplay"]
    assert result["repos"][1]["branch"] == "main"
    assert result["repos"][1]["projects"][0]["changed_files"] == 1


def test_get_projects_report_isolates_error_for_one_bad_path():
    responses = {
        ("git", "-C", "C:/missing", "rev-parse", "--show-toplevel"): _result(returncode=128, stdout=""),
        ("git", "-C", "C:/home/Odakla", "rev-parse", "--show-toplevel"): _result(stdout="C:/home\n"),
        ("git", "-C", "C:/home", "branch", "--show-current"): _result(stdout="master\n"),
        ("git", "-C", "C:/home", "status", "--porcelain", "--", "C:/home/Odakla"): _result(stdout=""),
        ("git", "-C", "C:/home", "log", "-1", "--format=%s|%ar", "--", "C:/home/Odakla"): _result(stdout=""),
    }

    def runner(args):
        return responses[tuple(args)]

    result = get_projects_report(
        projects=[("Broken", "C:/missing"), ("Odakla", "C:/home/Odakla")],
        runner=runner,
    )

    assert result["errors"] == [{"name": "Broken", "message": "Git deposu bulunamadı."}]
    assert len(result["repos"]) == 1
    assert result["repos"][0]["projects"][0]["last_commit"] is None


def test_get_projects_report_isolates_unexpected_exception_per_project():
    def runner(args):
        if args[2] == "C:/boom":
            raise FileNotFoundError("git bulunamadı")
        return _result(stdout="C:/home\n")

    result = get_projects_report(
        projects=[("Boom", "C:/boom"), ("Odakla", "C:/home")],
        runner=runner,
    )

    assert result["errors"] == [{"name": "Boom", "message": "Rapor alınamadı: git bulunamadı"}]
    assert len(result["repos"]) == 1
