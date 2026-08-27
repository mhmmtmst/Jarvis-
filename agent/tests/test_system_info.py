from unittest.mock import MagicMock, patch

from agent.tools.system_info import get_system_info


@patch("agent.tools.system_info.psutil")
def test_get_system_info_returns_expected_keys(mock_psutil):
    mock_psutil.cpu_percent.return_value = 12.3
    mock_psutil.virtual_memory.return_value = MagicMock(percent=45.6)
    mock_psutil.disk_usage.return_value = MagicMock(percent=70.1)
    mock_psutil.sensors_battery.return_value = MagicMock(percent=88)

    info = get_system_info()

    assert info == {
        "cpu_percent": 12.3,
        "ram_percent": 45.6,
        "disk_percent": 70.1,
        "battery_percent": 88,
    }


@patch("agent.tools.system_info.psutil")
def test_get_system_info_handles_missing_battery(mock_psutil):
    mock_psutil.cpu_percent.return_value = 5.0
    mock_psutil.virtual_memory.return_value = MagicMock(percent=20.0)
    mock_psutil.disk_usage.return_value = MagicMock(percent=30.0)
    mock_psutil.sensors_battery.return_value = None

    info = get_system_info()

    assert info["battery_percent"] is None
