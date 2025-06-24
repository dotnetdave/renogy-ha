import importlib.util
from pathlib import Path

# Dynamically load the harness module
HARNESS_PATH = Path(__file__).resolve().parents[1] / "tools" / "ble_test_harness.py"
spec = importlib.util.spec_from_file_location("ble_harness", HARNESS_PATH)
ble_harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ble_harness)


def test_parse_hex():
    data = ble_harness._parse_hex("(0x) 00-FF")
    assert data == bytes([0x00, 0xFF])


def test_decode_lines_numeric_packet():
    lines = ["AA-55-44-2E-E0-27-10-03-E8-00-FA-50-41-01"]
    results = ble_harness.decode_lines(lines)
    assert results[0]["packetType"] == "0x44"
    assert results[0]["bus_voltage"] == 12.0
    assert results[0]["state_of_charge"] == 80
