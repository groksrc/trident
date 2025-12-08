"""Boolean expression evaluator for edge conditions.

Supports:
    - Comparison: ==, !=, <, >, <=, >=
    - Boolean: and, or, not
    - Parentheses
    - Field access: output.field.subfield
    - Literals: strings, numbers, true, false, null
"""

import ast
import re
from typing import Any

from .errors import ConditionError
from .template import get_nested


# Tokenizer patterns
TOKEN_PATTERNS = [
    (r'\s+', None),  # Skip whitespace
    (r'==|!=|<=|>=|<|>', 'OP'),
    (r'\band\b', 'AND'),
    (r'\bor\b', 'OR'),
    (r'\bnot\b', 'NOT'),
    (r'\btrue\b', 'TRUE'),
    (r'\bfalse\b', 'FALSE'),
    (r'\bnull\b', 'NULL'),
    (r"'[^']*'", 'STRING'),
    (r'"[^"]*"', 'STRING'),
    (r'-?\d+\.?\d*', 'NUMBER'),
    (r'[a-zA-Z_][a-zA-Z0-9_.]*', 'IDENT'),
    (r'\(', 'LPAREN'),
    (r'\)', 'RPAREN'),
]


def tokenize(expr: str) -> list[tuple[str, str]]:
    """Tokenize a condition expression."""
    tokens = []
    pos = 0
    while pos < len(expr):
        matched = False
        for pattern, token_type in TOKEN_PATTERNS:
            regex = re.compile(pattern)
            match = regex.match(expr, pos)
            if match:
                if token_type:  # Skip None (whitespace)
                    tokens.append((token_type, match.group()))
                pos = match.end()
                matched = True
                break
        if not matched:
            raise ConditionError(f"Invalid character at position {pos}: {expr[pos]!r}")
    return tokens


class Parser:
    """Recursive descent parser for condition expressions."""

    def __init__(self, tokens: list[tuple[str, str]], context: dict[str, Any]):
        self.tokens = tokens
        self.context = context
        self.pos = 0

    def peek(self) -> tuple[str, str] | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self, expected_type: str | None = None) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise ConditionError("Unexpected end of expression")
        if expected_type and token[0] != expected_type:
            raise ConditionError(f"Expected {expected_type}, got {token[0]}")
        self.pos += 1
        return token

    def parse(self) -> bool:
        result = self.parse_or()
        if self.peek() is not None:
            raise ConditionError(f"Unexpected token: {self.peek()}")
        return result

    def parse_or(self) -> bool:
        left = self.parse_and()
        while self.peek() and self.peek()[0] == 'OR':
            self.consume('OR')
            right = self.parse_and()
            left = left or right
        return left

    def parse_and(self) -> bool:
        left = self.parse_not()
        while self.peek() and self.peek()[0] == 'AND':
            self.consume('AND')
            right = self.parse_not()
            left = left and right
        return left

    def parse_not(self) -> bool:
        if self.peek() and self.peek()[0] == 'NOT':
            self.consume('NOT')
            return not self.parse_not()
        return self.parse_comparison()

    def parse_comparison(self) -> bool:
        left = self.parse_term()
        if self.peek() and self.peek()[0] == 'OP':
            op = self.consume('OP')[1]
            right = self.parse_term()
            return self._compare(left, op, right)
        # Truthy check for standalone values
        return bool(left)

    def _compare(self, left: Any, op: str, right: Any) -> bool:
        match op:
            case '==': return left == right
            case '!=': return left != right
            case '<': return left < right
            case '>': return left > right
            case '<=': return left <= right
            case '>=': return left >= right
        raise ConditionError(f"Unknown operator: {op}")

    def parse_term(self) -> Any:
        token = self.peek()
        if token is None:
            raise ConditionError("Unexpected end of expression")

        match token[0]:
            case 'LPAREN':
                self.consume('LPAREN')
                result = self.parse_or()
                self.consume('RPAREN')
                return result
            case 'STRING':
                _, value = self.consume('STRING')
                return value[1:-1]  # Strip quotes
            case 'NUMBER':
                _, value = self.consume('NUMBER')
                return float(value) if '.' in value else int(value)
            case 'TRUE':
                self.consume('TRUE')
                return True
            case 'FALSE':
                self.consume('FALSE')
                return False
            case 'NULL':
                self.consume('NULL')
                return None
            case 'IDENT':
                _, name = self.consume('IDENT')
                return get_nested(self.context, name)
            case _:
                raise ConditionError(f"Unexpected token: {token}")


def evaluate(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a condition expression against a context.

    Args:
        expr: Condition expression (e.g., "output.intent != 'spam'")
        context: Variable context for field access

    Returns:
        Boolean result of evaluation

    Raises:
        ConditionError: If expression is invalid
    """
    try:
        tokens = tokenize(expr)
        if not tokens:
            return True  # Empty condition is truthy
        parser = Parser(tokens, context)
        return parser.parse()
    except ConditionError:
        raise
    except Exception as e:
        raise ConditionError(f"Error evaluating condition: {e}") from e
