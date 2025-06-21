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
