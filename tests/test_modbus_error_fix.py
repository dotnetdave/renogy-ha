import ast
import pytest


BLE_PATH = "custom_components/renogy/ble.py"


def _get_modbus_method():
    with open(BLE_PATH, "r") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_read_modbus_device":
            return node
    return None


def test_read_modbus_device_exists():
    method = _get_modbus_method()
    assert method is not None, "_read_modbus_device method not found"


def test_unboundlocalerror_protection():
    method = _get_modbus_method()
    assert method is not None
    src = ast.get_source_segment(open(BLE_PATH).read(), method)
    assert "locals().get('success'" in src
    assert "locals().get('error'" in src
