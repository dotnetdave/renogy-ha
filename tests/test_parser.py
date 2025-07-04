import pytest
import importlib.util
from pathlib import Path

PARSER_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "renogy" / "parser.py"
CONST_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "renogy" / "const.py"

spec_parser = importlib.util.spec_from_file_location("parser", PARSER_PATH)
parser = importlib.util.module_from_spec(spec_parser)
spec_parser.loader.exec_module(parser)

spec_const = importlib.util.spec_from_file_location("const", CONST_PATH)
const = importlib.util.module_from_spec(spec_const)
spec_const.loader.exec_module(const)

parse_shunt_packet = parser.parse_shunt_packet
parse_shunt_ble_packet = parser.parse_shunt_ble_packet
RENOGY_SHUNT_MANUF_ID = const.RENOGY_SHUNT_MANUF_ID


def test_parse_shunt_packet_valid():
    data = bytes(
        [
            (RENOGY_SHUNT_MANUF_ID >> 8) & 0xFF,
            RENOGY_SHUNT_MANUF_ID & 0xFF,
            0x2E,
            0xE0,
            0x27,
            0x10,
            0x03,
            0xE8,
            0x00,
            0xFA,
            0x50,
            0x41,
            0x01,
        ]
    )
    result = parse_shunt_packet(data)
    assert result["bus_voltage"] == 12.0
    assert result["shunt_drop"] == 10.0
    assert result["current"] == 1.0
    assert result["consumed_ah"] == 2.5
    assert result["state_of_charge"] == 80
    assert result["temperature"] == 25
    assert result["extra_flags"] == 1


def test_parse_shunt_packet_invalid_length():
    with pytest.raises(ValueError):
        parse_shunt_packet(b"\x00\x01\x02")


def test_parse_shunt_ble_packet_model_id():
    data = b"\x00\x01\x10RSSHUNT"
    result = parse_shunt_ble_packet(data)
    assert result["packetType"] == "0x10"
    assert result["model_id"] == "RSSHUNT"


def test_parse_shunt_ble_packet_numeric():
    data = bytes([
        0xAA,
        0x55,
        0x44,
        0x2E,
        0xE0,
        0x27,
        0x10,
        0x03,
        0xE8,
        0x00,
        0xFA,
        0x50,
        0x41,
        0x01,
    ])
    result = parse_shunt_ble_packet(data)
    assert result["packetType"] == "0x44"
    assert result["bus_voltage"] == 12.0
    assert result["shunt_drop"] == 10.0
    assert result["current"] == 1.0
    assert result["consumed_ah"] == 2.5
    assert result["state_of_charge"] == 80
    assert result["temperature"] == 25
    assert result["extra_flags"] == 1


def test_parse_shunt_ble_packet_group_battery_voltage():
    data = bytes.fromhex(
        "00-01-0C-05-06-06-00-9C-34-00-00-96-37".replace("-", "")
    )
    result = parse_shunt_ble_packet(data)
    assert result["packetType"] == "0x05"
    assert result["battery_voltage"] == 13.468


def test_parse_shunt_ble_packet_group_soc():
    data = bytes.fromhex("00-01-0C-03-0A-06-00-31-01-9B-EA".replace("-", ""))
    result = parse_shunt_ble_packet(data)
    assert result["packetType"] == "0x03"
    assert result["state_of_charge"] == 30.5


def test_parse_shunt_ble_packet_ascii_status():
    with pytest.raises(ValueError):
        parse_shunt_ble_packet(b"AT+NM=BW-RCS0005219\r\n")


def test_parse_shunt_ble_packet_bw_header():
    data = b"BW\x01\x05\x00\x13\x88\x00"
    result = parse_shunt_ble_packet(data)
    assert result["packetType"] == "0x05"
    assert result["battery_voltage"] == 5.0


def test_parse_shunt_ble_messages_merge():
    packets = [
        bytes.fromhex("00-01-0C-05-06-06-00-9C-34-00-00-96-37".replace("-", "")),
        bytes.fromhex("00-01-0C-03-0A-06-00-31-01-9B-EA".replace("-", "")),
    ]
    result = parser.parse_shunt_ble_messages(packets)
    assert result["battery_voltage"] == 13.468
    assert result["state_of_charge"] == 30.5

