from agent.config import load_config


def test_load_config_reads_provided_env_mapping():
    env = {
        "GEMINI_API_KEY": "test-key-123",
        "JARVIS_WS_HOST": "0.0.0.0",
        "JARVIS_WS_PORT": "9999",
        "JARVIS_GEMINI_MODEL": "gemini-test-model",
        "JARVIS_GEMINI_VOICE": "Puck",
        "JARVIS_WEATHER_LOCATION": "Safranbolu, Karabük",
        "JARVIS_REPORT_PROJECTS": "Odakla:C:/Odakla,Jarvis:C:/jarvis",
    }

    config = load_config(env=env)

    assert config.gemini_api_key == "test-key-123"
    assert config.ws_host == "0.0.0.0"
    assert config.ws_port == 9999
    assert config.gemini_model == "gemini-test-model"
    assert config.gemini_voice == "Puck"
    assert config.weather_location == "Safranbolu, Karabük"
    assert config.report_projects == "Odakla:C:/Odakla,Jarvis:C:/jarvis"


def test_load_config_has_sane_defaults_when_env_is_empty():
    config = load_config(env={})

    assert config.gemini_api_key == ""
    assert config.ws_host == "127.0.0.1"
    assert config.ws_port == 8765
    assert config.gemini_model == "gemini-3.1-flash-live-preview"
    assert config.gemini_voice == "Kore"
    assert config.weather_location == ""
    assert config.report_projects == ""


def test_load_config_reads_env_file_from_jarvis_env_path(tmp_path, monkeypatch):
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "GEMINI_API_KEY=from-custom-path\nJARVIS_GEMINI_VOICE=Zephyr\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_GEMINI_VOICE", raising=False)
    monkeypatch.setenv("JARVIS_ENV_PATH", str(env_file))

    config = load_config()

    assert config.gemini_api_key == "from-custom-path"
    assert config.gemini_voice == "Zephyr"
