"""Tests for template rendering."""

import unittest

from trident.template import get_nested, render


class TestGetNested(unittest.TestCase):
    def test_simple_key(self):
        self.assertEqual(get_nested({"a": 1}, "a"), 1)

    def test_nested_key(self):
        self.assertEqual(get_nested({"a": {"b": {"c": 3}}}, "a.b.c"), 3)

    def test_missing_key(self):
        self.assertIsNone(get_nested({"a": 1}, "b"))

    def test_missing_nested(self):
        self.assertIsNone(get_nested({"a": 1}, "a.b"))

    def test_non_dict_intermediate(self):
        self.assertIsNone(get_nested({"a": "string"}, "a.b"))


class TestRender(unittest.TestCase):
    def test_simple_var(self):
        self.assertEqual(render("Hello {{name}}", {"name": "World"}), "Hello World")

    def test_var_with_spaces(self):
        self.assertEqual(render("Hello {{ name }}", {"name": "World"}), "Hello World")

    def test_nested_var(self):
        self.assertEqual(render("Value: {{data.value}}", {"data": {"value": 42}}), "Value: 42")

    def test_unknown_var_unchanged(self):
        self.assertEqual(render("Hello {{unknown}}", {}), "Hello {{unknown}}")

    def test_multiple_vars(self):
        result = render("{{greeting}} {{name}}!", {"greeting": "Hello", "name": "World"})
        self.assertEqual(result, "Hello World!")

    def test_number_conversion(self):
        self.assertEqual(render("Count: {{n}}", {"n": 42}), "Count: 42")

    def test_deeply_nested(self):
        result = render("{{a.b.c.d}}", {"a": {"b": {"c": {"d": "deep"}}}})
        self.assertEqual(result, "deep")


if __name__ == "__main__":
    unittest.main()
