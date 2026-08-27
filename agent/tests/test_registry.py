import inspect
from functools import partial
from types import SimpleNamespace

from agent.tools.registry import build_tool_registry


def make_fake_client():
    return SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text="")))


def test_registry_contains_all_tools():
    registry = build_tool_registry(make_fake_client())

    assert set(registry.keys()) == {
        "open_app",
        "get_system_info",
        "open_browser",
        "run_command",
        "play_media",
        "read_screen",
        "remember",
        "recall",
        "delete_memory",
        "get_weather",
        "get_projects_report",
        "search_files",
    }


def test_open_app_tool_spec_declares_required_isim_parameter():
    spec = build_tool_registry(make_fake_client())["open_app"]

    assert spec.parameters["required"] == ["isim"]
    assert "isim" in spec.parameters["properties"]


def test_get_system_info_tool_spec_takes_no_parameters():
    spec = build_tool_registry(make_fake_client())["get_system_info"]

    assert spec.parameters["properties"] == {}


def test_tool_handlers_are_callable_and_return_dicts():
    registry = build_tool_registry(make_fake_client())

    result = registry["get_system_info"].handler()

    assert isinstance(result, dict)


def test_open_browser_tool_spec_declares_required_query_or_url_parameter():
    spec = build_tool_registry(make_fake_client())["open_browser"]

    assert spec.parameters["required"] == ["query_or_url"]


def test_run_command_tool_spec_declares_required_command_and_optional_cwd():
    spec = build_tool_registry(make_fake_client())["run_command"]

    assert spec.parameters["required"] == ["command"]
    assert "cwd" in spec.parameters["properties"]


def test_play_media_tool_spec_declares_required_query_parameter():
    spec = build_tool_registry(make_fake_client())["play_media"]

    assert spec.parameters["required"] == ["query"]


def test_read_screen_tool_spec_has_no_required_parameters():
    spec = build_tool_registry(make_fake_client())["read_screen"]

    assert spec.parameters["required"] == []


def test_remember_tool_spec_declares_required_key_and_value_parameters():
    spec = build_tool_registry(make_fake_client())["remember"]

    assert spec.parameters["required"] == ["key", "value"]
    assert "category" in spec.parameters["properties"]


def test_recall_tool_spec_takes_no_parameters():
    spec = build_tool_registry(make_fake_client())["recall"]

    assert spec.parameters["properties"] == {}


def test_delete_memory_tool_spec_has_no_required_parameters():
    spec = build_tool_registry(make_fake_client())["delete_memory"]

    assert spec.parameters["required"] == []
    assert {"category", "key", "match_text"} <= set(spec.parameters["properties"])


def test_read_screen_handler_is_bound_to_the_given_client():
    fake_client = make_fake_client()
    registry = build_tool_registry(fake_client)

    result = registry["read_screen"].handler(grabber=lambda: SimpleNamespace(save=lambda buf, format: None))

    assert result["status"] == "ok"


def test_every_schema_property_is_a_real_handler_parameter():
    registry = build_tool_registry(make_fake_client())
    for name, spec in registry.items():
        handler = spec.handler
        if isinstance(handler, partial):
            base_func, bound_kwargs = handler.func, set(handler.keywords)
        else:
            base_func, bound_kwargs = handler, set()
        real_params = set(inspect.signature(base_func).parameters) - bound_kwargs
        assert set(spec.parameters.get("properties", {})) <= real_params, name
        assert set(spec.parameters.get("required", [])) <= real_params, name


def test_get_projects_report_tool_spec_takes_no_parameters():
    spec = build_tool_registry(make_fake_client())["get_projects_report"]

    assert spec.parameters["properties"] == {}
    assert spec.parameters["required"] == []


def test_search_files_tool_spec_declares_required_query_and_optional_root():
    spec = build_tool_registry(make_fake_client())["search_files"]

    assert spec.parameters["required"] == ["query"]
    assert "root" in spec.parameters["properties"]


def test_get_projects_report_handler_is_bound_to_the_given_projects():
    registry = build_tool_registry(make_fake_client(), report_projects=[])

    result = registry["get_projects_report"].handler()

    assert result == {
        "status": "error",
        "message": "Hiç proje yapılandırılmamış (JARVIS_REPORT_PROJECTS boş).",
    }
