import psutil


def get_system_info() -> dict:
    """Snapshot of CPU/RAM/disk/battery usage, used both as a Gemini tool
    and as the payload for the HUD's periodic system-status broadcast."""
    battery = psutil.sensors_battery()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("C:\\").percent,
        "battery_percent": battery.percent if battery else None,
    }
