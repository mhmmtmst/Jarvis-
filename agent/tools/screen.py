import io

from google.genai import types

_DEFAULT_QUESTION = "Ekranda ne var, kısaca özetle."
_MODEL = "gemini-3.6-flash"


def read_screen(soru: str = _DEFAULT_QUESTION, grabber=None, client=None) -> dict:
    """Ekran görüntüsü alıp ayrı, senkron bir generate_content çağrısıyla
    (Live oturumundan bağımsız) Gemini'ye tarif ettirir. `grabber` testte
    enjekte edilir; gerçekte PIL.ImageGrab.grab kullanılır."""
    if grabber is None:
        from PIL import ImageGrab
        grabber = ImageGrab.grab

    try:
        image = grabber()
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        response = client.models.generate_content(
            model=_MODEL,
            contents=[types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"), soru],
        )
        return {"status": "ok", "description": response.text}
    except Exception as error:
        return {"status": "error", "message": f"Ekran okunamadı: {error}"}
