from types import SimpleNamespace

from agent.tools.screen import read_screen


class FakeImage:
    def save(self, buf, format):
        buf.write(b"fake-png-bytes")


def test_read_screen_calls_generate_content_with_image_and_question():
    calls = []

    class FakeModels:
        def generate_content(self, *, model, contents):
            calls.append({"model": model, "contents": contents})
            return SimpleNamespace(text="Kırmızı bir daire görüyorum.")

    fake_client = SimpleNamespace(models=FakeModels())

    result = read_screen(soru="Ne görüyorsun?", grabber=lambda: FakeImage(), client=fake_client)

    assert result == {"status": "ok", "description": "Kırmızı bir daire görüyorum."}
    assert calls[0]["model"] == "gemini-3.6-flash"
    assert calls[0]["contents"][1] == "Ne görüyorsun?"


def test_read_screen_uses_default_question_when_not_given():
    class FakeModels:
        def generate_content(self, *, model, contents):
            return SimpleNamespace(text="özet")

    fake_client = SimpleNamespace(models=FakeModels())

    result = read_screen(grabber=lambda: FakeImage(), client=fake_client)

    assert result["status"] == "ok"
    assert result["description"] == "özet"


def test_read_screen_returns_error_when_capture_fails():
    def failing_grabber():
        raise OSError("ekran erişilemedi")

    result = read_screen(grabber=failing_grabber, client=SimpleNamespace())

    assert result["status"] == "error"


def test_read_screen_returns_error_when_generate_content_fails():
    class FailingModels:
        def generate_content(self, *, model, contents):
            raise RuntimeError("API hatası")

    fake_client = SimpleNamespace(models=FailingModels())

    result = read_screen(grabber=lambda: FakeImage(), client=fake_client)

    assert result["status"] == "error"
