import ast
import importlib.util
from pathlib import Path

CF_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "renogy" / "config_flow.py"
CONST_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "renogy" / "const.py"

# Load constants
spec_const = importlib.util.spec_from_file_location("const", CONST_PATH)
const = importlib.util.module_from_spec(spec_const)
spec_const.loader.exec_module(const)

# Extract the _is_renogy_device function via AST to avoid importing Home Assistant deps
with open(CF_PATH, "r") as f:
    tree = ast.parse(f.read())

_is_renogy_device = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "_is_renogy_device":
        mod = ast.Module(body=[node], type_ignores=[])
        ns: dict = {}
        exec(
            compile(mod, CF_PATH.as_posix(), "exec"),
            {
                "RENOGY_NAME_PREFIXES": const.RENOGY_NAME_PREFIXES,
                "RENOGY_SHUNT_SERVICE_UUID": const.RENOGY_SHUNT_SERVICE_UUID,
                "BluetoothServiceInfoBleak": object,
            },
            ns,
        )
        _is_renogy_device = ns[node.name]
        break

class DummyInfo:
    def __init__(self, name=None, uuids=None):
        self.name = name
        self.service_uuids = uuids or []


def test_is_renogy_device_name_match():
    info = DummyInfo(name="RTMSmartShunt300")
    assert _is_renogy_device(None, info)  # type: ignore[arg-type]


def test_is_renogy_device_uuid_match():
    info = DummyInfo(name="Unknown", uuids=[const.RENOGY_SHUNT_SERVICE_UUID])
    assert _is_renogy_device(None, info)  # type: ignore[arg-type]


def test_is_renogy_device_no_match():
    info = DummyInfo(name="Other", uuids=["1234"])
    assert not _is_renogy_device(None, info)  # type: ignore[arg-type]
