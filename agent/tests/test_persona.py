from agent.persona import JARVIS_PERSONA


def test_persona_lists_get_projects_report_tool():
    assert "get_projects_report" in JARVIS_PERSONA


def test_persona_has_rapor_ver_example():
    assert "rapor ver" in JARVIS_PERSONA.lower()
