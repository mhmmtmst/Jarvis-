from agent.persona import JARVIS_PERSONA, build_persona


def test_persona_lists_get_projects_report_tool():
    assert "get_projects_report" in JARVIS_PERSONA


def test_persona_has_rapor_ver_example():
    assert "rapor ver" in JARVIS_PERSONA.lower()


def test_build_persona_relaxed_mode_equals_base_persona():
    assert build_persona("rahat") == JARVIS_PERSONA


def test_build_persona_defaults_to_relaxed_mode():
    assert build_persona() == JARVIS_PERSONA


def test_build_persona_work_mode_appends_focus_instruction_on_top_of_base():
    result = build_persona("calisma")

    assert result.startswith(JARVIS_PERSONA)
    assert "ÇALIŞMA" in result


def test_build_persona_unknown_mode_falls_back_to_base_persona():
    assert build_persona("bilinmeyen-mod") == JARVIS_PERSONA
