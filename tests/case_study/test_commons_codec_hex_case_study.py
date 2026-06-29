"""Apache Commons Codec Hex external case study (issue #656).

The assertions below are a focused pytest port of upstream ``HexTest`` cases from
Commons Codec 1.22.0. They run against the rule-layer translation linked by
``tests/case_study/commons_codec_hex_harness.py``.
"""

from __future__ import annotations

import pytest

from tests.case_study.commons_codec_hex_harness import (
    _RESIDUAL_GAP_PATCHES,
    link_commons_codec_hex_namespace,
)

_NS = link_commons_codec_hex_namespace()
Hex = _NS.Hex
ByteBuffer = _NS.ByteBuffer
DecoderException = _NS.DecoderException
EncoderException = _NS.EncoderException


def _utf8_bytes(value: str) -> list[int]:
    return list(value.encode("utf-8"))


def test_decode_hex_char_array_empty() -> None:
    assert Hex.decode_hex([]) == []


def test_decode_hex_string_empty() -> None:
    assert Hex.decode_hex("") == []


@pytest.mark.parametrize("data", [["A"], ["A", "B", "C"], ["A", "B", "C", "D", "E"], "6"])
def test_decode_hex_odd_characters_raise_decoder_exception(data: list[str] | str) -> None:
    with pytest.raises(DecoderException):
        Hex.decode_hex(data)


@pytest.mark.parametrize("data", [["q", "0"], ["0", "q"], "q0", "0q"])
def test_decode_hex_bad_character_raises_decoder_exception(data: list[str] | str) -> None:
    with pytest.raises(DecoderException):
        Hex.decode_hex(data)


def test_decode_hex_to_output_buffer() -> None:
    out = [0] * 8

    written = Hex.decode_hex(list("aabbccddeeff"), out, 1)

    assert written == 6
    assert out == [0, -86, -69, -52, -35, -18, -1, 0]


def test_decode_hex_output_buffer_too_small() -> None:
    with pytest.raises(DecoderException):
        Hex.decode_hex(list("aabbccddeeff"), [0] * 4, 0)


def test_encode_hex_byte_array_empty() -> None:
    assert Hex.encode_hex([]) == []
    assert Hex.encode_hex_string([]) == ""


def test_encode_hex_byte_array_hello_world_lower_case_hex() -> None:
    data = _utf8_bytes("Hello World")
    expected = "48656c6c6f20576f726c64"

    assert "".join(Hex.encode_hex(data)) == expected
    assert "".join(Hex.encode_hex(data, True)) == expected
    assert "".join(Hex.encode_hex(data, False)) != expected


def test_encode_hex_byte_array_hello_world_upper_case_hex() -> None:
    data = _utf8_bytes("Hello World")
    expected = "48656C6C6F20576F726C64"

    assert "".join(Hex.encode_hex(data)) != expected
    assert "".join(Hex.encode_hex(data, True)) != expected
    assert "".join(Hex.encode_hex(data, False)) == expected


def test_encode_hex_byte_array_zeroes() -> None:
    assert "".join(Hex.encode_hex([0] * 36)) == (
        "000000000000000000000000000000000000000000000000000000000000000000000000"
    )


def test_encode_hex_string_byte_array_boolean_case() -> None:
    assert Hex.encode_hex_string([10], True) == "0a"
    assert Hex.encode_hex_string([10], False) == "0A"


def test_encode_hex_partial_input() -> None:
    data = _utf8_bytes("hello world")

    assert Hex.encode_hex(data, 0, 0, True) == []
    assert Hex.encode_hex(data, 0, 1, True) == list("68")
    assert Hex.encode_hex(data, 0, 1, False) == list("68")
    assert Hex.encode_hex(data, 2, 4, True) == list("6c6c6f20")
    assert Hex.encode_hex(data, 2, 4, False) == list("6C6C6F20")
    assert Hex.encode_hex(data, 10, 1, True) == list("64")
    assert Hex.encode_hex(data, 10, 1, False) == list("64")


def test_encode_hex_to_output_buffer() -> None:
    out = ["?"] * 6

    result = Hex.encode_hex([10, -1], 0, 2, False, out, 1)

    assert result is None
    assert out == ["?", "0", "A", "F", "F", "?"]


def test_encode_hex_byte_buffer_consumes_remaining_array_backed_bytes() -> None:
    buffer = ByteBuffer.wrap(_utf8_bytes("Hello"))

    assert "".join(Hex.encode_hex(buffer)) == "48656c6c6f"
    assert buffer.remaining() == 0
    assert buffer.position() == 5


def test_encode_hex_byte_buffer_copies_only_remaining_slice() -> None:
    buffer = ByteBuffer.wrap(_utf8_bytes("xHex!"), expose_array=False)
    buffer.position(1)
    buffer.limit(4)

    assert "".join(Hex.encode_hex(buffer, False)) == "486578"
    assert buffer.remaining() == 0
    assert buffer.position() == 4


def test_byte_buffer_put_respects_configured_limit() -> None:
    buffer = ByteBuffer.allocate(4)
    buffer.limit(2)

    buffer.put([1, 2])
    with pytest.raises(IndexError):
        buffer.put(3)


def test_decode_byte_buffer_uses_configured_utf8_charset_and_consumes_buffer() -> None:
    buffer = ByteBuffer.wrap(_utf8_bytes("48656c6c6f"))

    assert Hex().decode(buffer) == _utf8_bytes("Hello")
    assert buffer.remaining() == 0


def test_encode_decode_signed_byte_values() -> None:
    data = [0, 1, 15, 16, 127, -128, -1]

    encoded = Hex.encode_hex(data)

    assert "".join(encoded) == "00010f107f80ff"
    assert Hex.decode_hex(encoded) == data


def test_translation_metrics_record_rule_only_surface() -> None:
    assert set(_NS.metrics) == {
        "BinaryDecoder",
        "BinaryEncoder",
        "DecoderException",
        "EncoderException",
        "Hex",
    }
    assert all(metric.coverage == 1.0 for metric in _NS.metrics.values())
    assert sum(metric.todos for metric in _NS.metrics.values()) == 0
    assert _NS.metrics["Hex"].semantic_warnings <= 60


def test_external_stubs_are_separate_from_residual_patches() -> None:
    assert _NS.external_stubs == (
        "ByteBuffer",
        "CharEncoding",
        "Character",
        "Charset",
        "StandardCharsets",
    )


def test_residual_gap_inventory() -> None:
    applied = set(_NS.applied_gaps)
    declared = {gap.gap_id for gap in _RESIDUAL_GAP_PATCHES}
    assert applied == declared


def test_exception_classes_are_linked() -> None:
    assert issubclass(DecoderException, Exception)
    assert issubclass(EncoderException, Exception)
