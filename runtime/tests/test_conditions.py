"""Tests for condition evaluation."""

import unittest

from trident.conditions import evaluate


class TestConditions(unittest.TestCase):
    def test_equality(self):
        self.assertTrue(evaluate("x == 1", {"x": 1}))
        self.assertFalse(evaluate("x == 2", {"x": 1}))

    def test_inequality(self):
        self.assertTrue(evaluate("x != 1", {"x": 2}))
        self.assertFalse(evaluate("x != 1", {"x": 1}))

    def test_comparison(self):
        self.assertTrue(evaluate("x > 5", {"x": 10}))
        self.assertTrue(evaluate("x < 5", {"x": 3}))
        self.assertTrue(evaluate("x >= 5", {"x": 5}))
        self.assertTrue(evaluate("x <= 5", {"x": 5}))

    def test_string_equality(self):
        self.assertTrue(evaluate("intent == 'spam'", {"intent": "spam"}))
        self.assertFalse(evaluate("intent == 'spam'", {"intent": "support"}))

    def test_and_operator(self):
        ctx = {"a": True, "b": True}
        self.assertTrue(evaluate("a and b", ctx))
        ctx["b"] = False
        self.assertFalse(evaluate("a and b", ctx))

    def test_or_operator(self):
        self.assertTrue(evaluate("a or b", {"a": False, "b": True}))
        self.assertFalse(evaluate("a or b", {"a": False, "b": False}))

    def test_not_operator(self):
        self.assertTrue(evaluate("not a", {"a": False}))
        self.assertFalse(evaluate("not a", {"a": True}))

    def test_parentheses(self):
        self.assertTrue(evaluate("(a or b) and c", {"a": True, "b": False, "c": True}))
        self.assertFalse(evaluate("a or (b and c)", {"a": False, "b": True, "c": False}))

    def test_nested_field_access(self):
        self.assertTrue(evaluate("output.intent == 'support'", {"output": {"intent": "support"}}))

    def test_complex_condition(self):
        ctx = {"output": {"intent": "support", "confidence": 0.9}}
        self.assertTrue(evaluate("output.intent != 'spam' and output.confidence > 0.5", ctx))

    def test_boolean_literals(self):
        self.assertTrue(evaluate("true", {}))
        self.assertFalse(evaluate("false", {}))

    def test_null_literal(self):
        self.assertTrue(evaluate("x == null", {"x": None}))

    def test_empty_condition(self):
        self.assertTrue(evaluate("", {}))

    def test_truthy_value(self):
        self.assertTrue(evaluate("x", {"x": 1}))
        self.assertFalse(evaluate("x", {"x": 0}))


if __name__ == "__main__":
    unittest.main()
