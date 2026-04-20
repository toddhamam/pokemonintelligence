"""AST check: live score() MUST NOT read retrospective/forward-looking columns.

Codex review v2 finding #4: live confidence must use only trailing data. Forward
validation lives on `score_snapshot.retrospective_validation_score` — populated by
retrospective_validate() — and must never be read by score(). This test walks the
miami_scoring source tree and fails the build on violations.
"""

from __future__ import annotations

import ast
from pathlib import Path

import miami_scoring
from miami_scoring.engine import FORBIDDEN_FORWARD_READ_FIELDS

SCORING_PACKAGE = Path(miami_scoring.__file__).parent
# Files we deliberately allow to reference forbidden names (whitelisted because
# they are either backtest/retrospective glue or the policy-declaration itself).
ALLOW_LIST = {
    "engine.py",  # declares FORBIDDEN_FORWARD_READ_FIELDS and the guard
    "retrospective.py",  # backtest-only — writes forbidden fields, never read by score()
}


def _iter_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if p.is_file()]


class _Walker(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[tuple[int, str]] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in FORBIDDEN_FORWARD_READ_FIELDS:
            self.violations.append((node.lineno, ast.unparse(node)))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_FORWARD_READ_FIELDS:
            self.violations.append((node.lineno, node.id))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        # Catch string-literal references like columns listed in raw SQL.
        if isinstance(node.value, str):
            for field in FORBIDDEN_FORWARD_READ_FIELDS:
                if field in node.value:
                    self.violations.append((node.lineno, node.value[:120]))
        self.generic_visit(node)


def test_live_score_has_no_forward_reads() -> None:
    violations: list[str] = []
    for path in _iter_files(SCORING_PACKAGE):
        if path.name in ALLOW_LIST:
            continue
        walker = _Walker()
        walker.visit(ast.parse(path.read_text()))
        for line, source in walker.violations:
            violations.append(f"{path.relative_to(SCORING_PACKAGE)}:{line}: {source}")
    assert not violations, "Forward-read violations in live scoring path:\n" + "\n".join(violations)
