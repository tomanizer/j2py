"""Tests for selector and transform helper modules."""

from j2py.parse.java_ast import parse_source
from j2py.translate.selectors import And, HasChild, NodeType, Not, Or, Text, TextIn, apply_rules
from j2py.translate.transforms import keyword_safe, make_const, null_to_none, this_to_self


def test_selectors_match_nodes_and_apply_rules() -> None:
    parsed = parse_source("public class Sample { private int count; }")
    class_node = next(parsed.root.find_all("class_declaration"))
    identifier = class_node.child_by_field("name")
    assert identifier is not None

    assert NodeType("class_declaration").matches(class_node)
    assert Text("Sample").matches(identifier)
    assert TextIn("Sample", "Other").matches(identifier)
    assert HasChild(Text("Sample")).matches(class_node)
    assert And(NodeType("identifier"), Text("Sample")).matches(identifier)
    assert Or(Text("Missing"), Text("Sample")).matches(identifier)
    assert Not(Text("Missing")).matches(identifier)
    assert apply_rules(identifier, [(Text("Sample"), make_const("Renamed"))]) == "Renamed"


def test_transforms_return_expected_tokens() -> None:
    null_node = next(parse_source("class A { Object value = null; }").root.find_all("null_literal"))
    this_node = next(parse_source("class A { A get() { return this; } }").root.find_all("this"))
    keyword_node = next(parse_source("class A { int className; }").root.find_all("identifier"))

    assert null_to_none(null_node) == "None"
    assert this_to_self(this_node) == "self"
    assert keyword_safe(keyword_node) is None
