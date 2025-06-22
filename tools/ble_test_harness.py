#!/usr/bin/env python3
"""Simple harness to decode Renogy BLE notification data."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List


try:
    # Optional dependency used by the integration
    from renogy_ble import RenogyParser  # type: ignore
    HAVE_RENOGY_BLE = True
except Exception:  # pragma: no cover - library may not be installed in tests
    RenogyParser = None
    HAVE_RENOGY_BLE = False

# Local fallback parser
# Import the parser module directly by path to avoid importing Home Assistant
# dependencies when running this harness standalone.
from importlib import util as _import_util
from pathlib import Path

PARSER_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "renogy"
    / "parser.py"
)

spec = _import_util.spec_from_file_location("parser", PARSER_PATH)
_parser = _import_util.module_from_spec(spec)
spec.loader.exec_module(_parser)  # type: ignore

parse_shunt_ble_packet = _parser.parse_shunt_ble_packet


def _parse_hex(hex_string: str) -> bytes:
    """Convert a string of the form '00-01-AA' or '0001AA' to bytes."""
    cleaned = hex_string.strip().replace("(0x)", "").replace("-", "").replace(" ", "")
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]
    return bytes.fromhex(cleaned)


def decode_payload(payload: bytes, register: int = 0) -> dict:
    """Decode a payload using renogy_ble if available or fallback parser."""
    if HAVE_RENOGY_BLE and RenogyParser:
        try:
            return RenogyParser.parse(payload, "shunt", register)
        except Exception as exc:  # pragma: no cover - runtime aid only
            return {"error": str(exc)}
    # Fallback handles only SmartShunt SOC packets (0x0C03)
    try:
        return parse_shunt_ble_packet(payload)
    except Exception as exc:  # pragma: no cover - runtime aid only
        return {"error": str(exc)}


def decode_lines(lines: Iterable[str]) -> List[dict]:
    """Decode all lines and return list of parsed dictionaries."""
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        payload = _parse_hex(line)
        results.append(decode_payload(payload))
    return results


def main() -> None:
    """Run the harness from the command line."""
    if len(sys.argv) < 2:
        print("Usage: ble_test_harness.py <hex-string>|<file> [more...]")
        print("Provide hex strings directly or paths to files containing them.")
        sys.exit(1)

    inputs: List[str] = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.exists():
            inputs.extend([l.strip() for l in path.read_text().splitlines() if l.strip()])
        else:
            inputs.append(arg)

    results = decode_lines(inputs)
    for src, res in zip(inputs, results):
        print(f"{src} -> {res}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
