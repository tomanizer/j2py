"""jsemver external end-to-end case study (issue #613).

Ports the library's own ``StreamTest`` JUnit 5 suite
(``com.github.zafarkhaja.semver.util.StreamTest``, jsemver v0.10.2, MIT) to pytest and
runs it against the **rule-layer translation** of the vendored ``util`` package, linked
by ``tests/case_study/jsemver_harness.py``.

This is the behavioural oracle for the first external conversion case study: the assertions
mirror the upstream JUnit cases one-for-one, so a green run means the translated Python is
behaviourally equivalent to the Java for the exercised surface. The residual translator
defects that had to be patched for the loop to close are asserted explicitly in
``test_residual_gap_inventory`` and documented in docs/CASE_STUDY_JSEMVER.md.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from tests.case_study.jsemver_harness import _RESIDUAL_GAP_PATCHES, link_util_namespace

_NS = link_util_namespace()
Stream = _NS.Stream
UnexpectedElementException = _NS.UnexpectedElementException


def _et(predicate: Callable[[Any], bool]) -> Any:
    """Wrap a predicate as a ``Stream.ElementType`` (the Java functional interface).

    Upstream tests pass lambdas where a ``Stream.ElementType`` is expected; the translated
    ``consume``/``positiveLookahead*`` call ``.is_matched_by(...)`` on each argument, so the
    oracle supplies a tiny concrete implementation rather than a bare lambda.
    """

    class _ElementType:
        def is_matched_by(self, element: Any) -> bool:
            return predicate(element)

    return _ElementType()


def _stream(*chars: str) -> Any:
    return Stream(list(chars))


def test_should_be_backed_by_array() -> None:
    chars = ["a", "b", "c"]
    stream = Stream(list(chars))
    assert stream.to_array() == chars


def test_should_implement_iterable() -> None:
    chars = ["a", "b", "c"]
    stream = Stream(list(chars))
    it = stream.iterator()
    for chr_ in chars:
        assert it.next_() == chr_
    assert it.has_next() is False


def test_should_not_return_real_elements_array() -> None:
    stream = _stream("a", "b", "c")
    char_array = stream.to_array()
    char_array[0] = "z"
    assert char_array[0] == "z"
    assert stream.to_array()[0] == "a"


def test_should_return_array_of_elements_that_are_left_in_stream() -> None:
    stream = _stream("a", "b", "c")
    stream.consume()
    stream.consume()
    assert len(stream.to_array()) == 1
    assert stream.to_array()[0] == "c"


def test_should_consume_elements_one_by_one() -> None:
    stream = _stream("a", "b", "c")
    assert stream.consume() == "a"
    assert stream.consume() == "b"
    assert stream.consume() == "c"


def test_should_raise_error_when_unexpected_element_consumed() -> None:
    stream = _stream("a", "b", "c")
    with pytest.raises(UnexpectedElementException) as exc_info:
        stream.consume(_et(lambda element: False))
    assert exc_info.value.get_message() is not None


def test_should_lookahead_without_consuming() -> None:
    stream = _stream("a", "b", "c")
    assert stream.lookahead() == "a"
    assert stream.lookahead() == "a"


def test_should_lookahead_arbitrary_number_of_elements() -> None:
    stream = _stream("a", "b", "c")
    assert stream.lookahead(1) == "a"
    assert stream.lookahead(2) == "b"
    assert stream.lookahead(3) == "c"


def test_should_check_if_lookahead_is_of_expected_types() -> None:
    stream = _stream("a", "b", "c")
    assert stream.positive_lookahead(_et(lambda e: e == "a")) is True
    assert stream.positive_lookahead(_et(lambda e: e == "c")) is False


def test_should_check_if_element_of_expected_types_exist_before_given_type() -> None:
    stream = _stream("1", ".", "0", ".", "0")
    assert (
        stream.positive_lookahead_before(_et(lambda e: e == "."), _et(lambda e: e == "1")) is True
    )
    assert (
        stream.positive_lookahead_before(_et(lambda e: e == "1"), _et(lambda e: e == ".")) is False
    )


def test_should_check_if_element_of_expected_types_exist_until_given_position() -> None:
    stream = _stream("1", ".", "0", ".", "0")
    assert stream.positive_lookahead_until(3, _et(lambda e: e == "0")) is True
    assert stream.positive_lookahead_until(3, _et(lambda e: e == "a")) is False


def test_should_push_back_one_element_at_a_time() -> None:
    stream = _stream("a", "b", "c")
    assert stream.consume() == "a"
    stream.push_back()
    assert stream.consume() == "a"


def test_should_stop_pushing_back_when_there_are_no_elements() -> None:
    stream = _stream("a", "b", "c")
    assert stream.consume() == "a"
    assert stream.consume() == "b"
    assert stream.consume() == "c"
    stream.push_back()
    stream.push_back()
    stream.push_back()
    stream.push_back()
    assert stream.consume() == "a"


def test_should_keep_track_of_current_offset() -> None:
    stream = _stream("a", "b", "c")
    assert stream.current_offset() == 0
    stream.consume()
    assert stream.current_offset() == 1
    stream.consume()
    stream.consume()
    assert stream.current_offset() == 3


def test_residual_gap_inventory() -> None:
    """Lock the residual translator-defect list this case study reports.

    If a future rule-layer change fixes one of these gaps, drop the corresponding patch
    from ``jsemver_harness._RESIDUAL_GAP_PATCHES`` and update docs/CASE_STUDY_JSEMVER.md.
    """
    applied = set(_NS.applied_gaps)
    declared = {gap.gap_id for gap in _RESIDUAL_GAP_PATCHES}
    # Every documented gap is a real defect that actually fired on the current output.
    assert (
        applied
        == declared
        == {
            "JSEMVER-5",
        }
    )
