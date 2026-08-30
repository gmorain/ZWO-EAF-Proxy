"""The two Focuser interfaces must stay in step.

`focuser.py` and `firmware/main/include/focuser.h` are the same contract written
twice, once per vehicle. They are kept in sync by hand, which is exactly the kind
of promise that quietly stops being true. This test is the enforcement.

The only intended difference is naming: snake_case in Python, camelCase in C++.
Operations, return types and the unsupported sentinel are the same on both.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIRMWARE = REPO / "firmware" / "main" / "include" / "focuser.h"
PYTHON = REPO / "host" / "src" / "zwoproxy" / "focuser.py"

# The contract is written in C++ types on one side and annotations on the other.
# A return type absent here is a deliberate stop: decide what it means on the
# other vehicle rather than letting the test wave it through.
RETURN_TYPES = {"bool": "bool", "int32_t": "int", "void": "None"}

# Same, for the value `kUnsupported` is defined as.
SENTINELS = {"INT32_MIN": -(2**31)}


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _firmware_body() -> str:
    source = FIRMWARE.read_text()
    return source[source.index("class Focuser") :]


def _python_body() -> str:
    source = PYTHON.read_text()
    return source[source.index("class Focuser") :]


def firmware_methods() -> dict[str, str]:
    """camelCase name -> C++ return type."""
    found = re.findall(r"virtual\s+([\w:*&<>]+)\s+(\w+)\s*\(", _firmware_body())
    return {name: kind for kind, name in found if name != "Focuser"}


def python_methods() -> dict[str, str]:
    """snake_case name -> return annotation."""
    body = _python_body()
    signature = re.compile(r"^    def (\w+)\s*\([^)]*\)\s*->\s*(.+?)\s*:", re.MULTILINE)
    declared = set(re.findall(r"^    def (\w+)\s*\(", body, re.MULTILINE))
    annotated = {name: kind.strip() for name, kind in signature.findall(body)}
    missing = sorted(declared - set(annotated))
    assert not missing, f"no return annotation, so it cannot be compared: {missing}"
    return annotated


def test_both_interfaces_declare_the_same_operations():
    firmware = set(firmware_methods())
    python = {camel(name) for name in python_methods()}
    assert firmware, "parsed no methods from focuser.h; the parser is stale"
    only_firmware = sorted(firmware - python)
    only_python = sorted(python - firmware)
    assert not only_firmware, f"in firmware, absent from Python: {only_firmware}"
    assert not only_python, f"in Python, absent from firmware: {only_python}"


def test_both_interfaces_agree_on_return_types():
    firmware = firmware_methods()
    python = {camel(name): kind for name, kind in python_methods().items()}
    for name, cxx in sorted(firmware.items()):
        expected = RETURN_TYPES.get(cxx)
        assert expected, f"{name} returns {cxx!r}, which RETURN_TYPES does not map"
        assert python[name] == expected, (
            f"{name} returns {cxx!r} in firmware, annotated {python[name]!r} in Python"
        )


def test_the_unsupported_sentinel_is_the_same_value():
    """A backend that cannot answer says so with this. Two spellings, one value."""
    from zwoproxy.focuser import UNSUPPORTED

    match = re.search(r"kUnsupported\s*=\s*(\w+)\s*;", FIRMWARE.read_text())
    assert match, "focuser.h no longer defines kUnsupported"
    expected = SENTINELS.get(match.group(1))
    assert expected is not None, f"kUnsupported is {match.group(1)!r}, unmapped"
    assert expected == UNSUPPORTED


def test_the_simulated_focuser_implements_the_whole_interface():
    from zwoproxy.backends.simulated import SimulatedFocuser

    for name in python_methods():
        assert callable(getattr(SimulatedFocuser, name, None)), f"SimulatedFocuser lacks {name}"


def test_the_simulated_focuser_returns_the_declared_types():
    """The interface can be right while a backend quietly returns None."""
    from zwoproxy.backends.simulated import SimulatedFocuser

    kinds = {"bool": bool, "int": int, "None": type(None)}
    calls = {"move_to": (0,), "set_position": (0,)}
    focuser = SimulatedFocuser(position=0)
    for name, annotation in python_methods().items():
        got = getattr(focuser, name)(*calls.get(name, ()))
        assert isinstance(got, kinds[annotation]), (
            f"{name} is annotated -> {annotation}, returned {got!r}"
        )
