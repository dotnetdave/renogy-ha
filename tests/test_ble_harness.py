import importlib.util
from pathlib import Path

# Dynamically load the harness module
HARNESS_PATH = Path(__file__).resolve().parents[1] / "tools" / "ble_test_harness.py"
spec = importlib.util.spec_from_file_location("ble_harness", HARNESS_PATH)
ble_harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ble_harness)

PARSER_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "renogy" / "parser.py"
spec_parser = importlib.util.spec_from_file_location("parser", PARSER_PATH)
parser = importlib.util.module_from_spec(spec_parser)
spec_parser.loader.exec_module(parser)


def test_parse_hex():
    data = ble_harness._parse_hex("(0x) 00-FF")
    assert data == bytes([0x00, 0xFF])


def test_decode_lines_numeric_packet():
    lines = ["AA-55-44-2E-E0-27-10-03-E8-00-FA-50-41-01"]
    results = ble_harness.decode_lines(lines)
    assert results[0]["packetType"] == "0x44"
    assert results[0]["bus_voltage"] == 12.0
    assert results[0]["state_of_charge"] == 80


def test_decode_lines_group_packet():
    lines = ["00-01-0C-03-0A-06-00-31-01-9B-EA"]
    results = ble_harness.decode_lines(lines)
    assert results[0]["packetType"] == "0x03"
    assert results[0]["state_of_charge"] == 30.5


def test_decode_lines_multi_packet():
    lines = [
        "00-01-0C-05-06-06-00-9C-34-00-00-96-37",
        "00-01-0C-03-0A-06-00-31-01-9B-EA",
    ]
    results = ble_harness.decode_lines(lines)
    merged = parser.parse_shunt_ble_messages([ble_harness._parse_hex(l) for l in lines])
    assert merged["battery_voltage"] == 13.468
    assert merged["state_of_charge"] == 30.5

