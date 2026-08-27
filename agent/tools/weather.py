import requests

REQUEST_TIMEOUT = 10


def get_weather_summary(location: str = "", default_location: str = "", http_get=None) -> dict:
    """wttr.in üzerinden hava durumu özeti döner. `location` (Gemini'nin
    doldurduğu, kullanıcının açıkça sorduğu yer) öncelikli; o da boşsa
    `default_location` (kullanıcının .env'de sabitlediği ev konumu, IP
    tespiti şehir bazında yanlış çıkabildiği için) kullanılır; o da boşsa
    wttr.in isteği yapan IP'den konumu kendisi tespit eder."""
    if http_get is None:
        http_get = requests.get

    target = location.strip() or default_location.strip()
    url = f"https://wttr.in/{target}" if target else "https://wttr.in/"

    try:
        response = http_get(url, params={"format": "j1"}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except Exception as error:
        return {"status": "error", "message": f"Hava durumu bilgisi alınamadı: {error}"}

    try:
        area = (payload["nearest_area"] or [{}])[0]
        region = ((area.get("region") or [{}])[0]).get("value", "").strip()
        area_name = ((area.get("areaName") or [{}])[0]).get("value", "").strip()
        city = target or region or area_name

        current = (payload["current_condition"] or [{}])[0]
        temp_c = current.get("temp_C")
        feels_like_c = current.get("FeelsLikeC")
        humidity = current.get("humidity")
        condition = ((current.get("weatherDesc") or [{}])[0]).get("value", "").strip()
    except (KeyError, IndexError, TypeError) as error:
        return {"status": "error", "message": f"Hava durumu verisi çözümlenemedi: {error}"}

    label = city or "Bulunduğun konum"
    return {
        "status": "ok",
        "city": city or "Bilinmeyen konum",
        "temp_c": temp_c,
        "condition": condition,
        "humidity": humidity,
        "feels_like_c": feels_like_c,
        "message": f"{label} için hava durumu: {temp_c} derece, {condition.lower()}.",
    }
