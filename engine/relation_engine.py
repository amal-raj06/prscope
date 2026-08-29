"""
PRScope — engine/relation_engine.py
------------------------------------
Deterministic rule engine: classifies a PR pair as CONFLICT / DEPENDENCY /
INDEPENDENT, based on the "defines vs. modifies" distinction.

This is the successor to the overlap check in tree_sitter_poc.py — same
underlying symbol data (functions/classes defined, call_leaf_names, and
enclosing hunk-context lines per PR), but now it returns an actual label
with evidence, not just an overlap set.

RULE:
  - A symbol appearing as ENCLOSING CONTEXT for a PR (git shows it after
    the @@ hunk header, but it's NOT in that PR's own added-lines
    definitions) means that PR is editing the INSIDE of something that
    already existed — i.e. modifying its behavior.
  - A symbol appearing in a PR's own function/class definitions means
    that PR is DEFINING it fresh.

  CONFLICT:    PR modifies a symbol the other PR calls or relies on,
               OR both PRs modify the same symbol's body.
  DEPENDENCY:  PR defines a symbol the other PR calls (and it isn't
               already flagged as a conflict via modification).
  INDEPENDENT: neither of the above.

Usage as a library:
    from relation_engine import classify_pair
    label, evidence = classify_pair(symbols_a, contexts_a, symbols_b, contexts_b)

`symbols_x` is the dict returned by extract_symbols() in tree_sitter_poc.py
(keys: functions, classes, calls, call_leaf_names, imports).
`contexts_x` is the list of enclosing-context strings from
extract_added_code_and_context() in tree_sitter_poc.py.
"""

import re
from dataclasses import dataclass, field

# ---------- symbol-name extraction from a hunk-context line ----------

def extract_symbol_name_from_signature(line: str):
    """
    Pulls a function or class name out of a git hunk-context line, e.g.
    'def make_default_short_help(help: str, max_length: int = 45) -> str:'
    -> 'make_default_short_help'
    or 'class Foo(Bar):' -> 'Foo'
    Returns None if the line doesn't look like a def/class signature.
    """
    m = re.match(r"\s*(?:async\s+)?def\s+(\w+)", line)
    if m:
        return m.group(1)
    m = re.match(r"\s*class\s+(\w+)", line)
    if m:
        return m.group(1)
    return None


# ---------- per-PR symbol sets ----------

def get_defined_symbols(symbols: dict) -> set:
    """Symbols this PR newly defines in its added lines."""
    return set(symbols["functions"]) | set(symbols["classes"])


def get_modified_symbols(contexts: list) -> set:
    """
    Symbols this PR is editing the INSIDE of, inferred from enclosing
    hunk-context lines (git shows you which function/class you're inside,
    even if that function/class itself isn't newly defined in this diff).
    """
    modified = set()
    for ctx_line in contexts:
        name = extract_symbol_name_from_signature(ctx_line)
        if name:
            modified.add(name)
    return modified


def get_called_symbols(symbols: dict) -> set:
    return set(symbols["call_leaf_names"])


# ---------- classification result ----------

@dataclass
class RelationResult:
    label: str  # "CONFLICT" | "DEPENDENCY" | "INDEPENDENT"
    conflict_evidence: set = field(default_factory=set)
    dependency_evidence: set = field(default_factory=set)

    def __str__(self):
        if self.label == "CONFLICT":
            return f"CONFLICT (evidence: {sorted(self.conflict_evidence)})"
        if self.label == "DEPENDENCY":
            return f"DEPENDENCY (evidence: {sorted(self.dependency_evidence)})"
        return "INDEPENDENT"


def classify_pair(symbols_a: dict, contexts_a: list,
                   symbols_b: dict, contexts_b: list) -> RelationResult:
    a_defined = get_defined_symbols(symbols_a)
    a_modified = get_modified_symbols(contexts_a)
    a_calls = get_called_symbols(symbols_a)

    b_defined = get_defined_symbols(symbols_b)
    b_modified = get_modified_symbols(contexts_b)
    b_calls = get_called_symbols(symbols_b)

    # CONFLICT: either side MODIFIES (not just defines) a symbol the
    # other side depends on, or both sides modify the same symbol.
    conflict_evidence = set()
    conflict_evidence |= (a_modified & b_calls)
    conflict_evidence |= (b_modified & a_calls)
    conflict_evidence |= (a_modified & b_modified)

    if conflict_evidence:
        return RelationResult(label="CONFLICT", conflict_evidence=conflict_evidence)

    # DEPENDENCY: one side DEFINES a symbol the other side calls.
    dependency_evidence = set()
    dependency_evidence |= (a_defined & b_calls)
    dependency_evidence |= (b_defined & a_calls)

    if dependency_evidence:
        return RelationResult(label="DEPENDENCY", dependency_evidence=dependency_evidence)

    return RelationResult(label="INDEPENDENT")


# ---------- self-test using the two real, already-validated examples ----------

def _self_test():
    """
    Fixtures below are copied directly from your real tree_sitter_poc.py
    output on the click pool (PR-05/PR-26 = CONFLICT, PR-08/PR-05 =
    DEPENDENCY), so this test proves the engine agrees with ground truth
    on data you've already seen — not synthetic data.
    """
    # --- CONFLICT case: PR-05 (A) vs PR-26 (B), click pool ---
    symbols_a1 = {
        "functions": ["short_help", "test_short_help_returns_first_sentence"],
        "classes": [],
        "calls": ["make_default_short_help", "short_help"],
        "call_leaf_names": ["make_default_short_help", "short_help"],
        "imports": [],
    }
    contexts_a1 = []
    symbols_b1 = {
        "functions": [],
        "classes": [],
        "calls": [],
        "call_leaf_names": [],
        "imports": [],
    }
    contexts_b1 = ["def make_default_short_help(help: str, max_length: int = 45) -> str:"]

    result1 = classify_pair(symbols_a1, contexts_a1, symbols_b1, contexts_b1)
    print(f"CONFLICT example  -> got: {result1}   (expected: CONFLICT)")
    assert result1.label == "CONFLICT", "FAILED: expected CONFLICT"

    # --- DEPENDENCY case: PR-08 (A) vs PR-05 (B), click pool ---
    symbols_a2 = {
        "functions": ["bridged_short_help", "test_bridged_short_help"],
        "classes": [],
        "calls": ["bridged_short_help", "short_help"],
        "call_leaf_names": ["bridged_short_help", "short_help"],
        "imports": [],
    }
    contexts_a2 = []
    symbols_b2 = {
        "functions": ["short_help", "test_short_help_returns_first_sentence"],
        "classes": [],
        "calls": ["make_default_short_help", "short_help"],
        "call_leaf_names": ["make_default_short_help", "short_help"],
        "imports": [],
    }
    contexts_b2 = []

    result2 = classify_pair(symbols_a2, contexts_a2, symbols_b2, contexts_b2)
    print(f"DEPENDENCY example -> got: {result2}   (expected: DEPENDENCY)")
    assert result2.label == "DEPENDENCY", "FAILED: expected DEPENDENCY"

    print("\nAll self-tests passed.")


if __name__ == "__main__":
    _self_test()