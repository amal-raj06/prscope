"""
PRScope — Step 3: Tree-sitter proof-of-concept
-------------------------------------------------
Takes ONE real CONFLICT example and ONE real DEPENDENCY example from
combined_python_pairs.json, feeds both PRs' diffs into Tree-sitter, and
prints out what gets extracted: function/class definitions, function
calls, and imports touched by each PR.

This is a proof-of-concept, not the final parser. Goal: confirm
Tree-sitter can actually pull structural symbols out of our real
BulkPR-Bench diffs before we build the full relation engine on top.

Usage:
    python tree_sitter_poc.py --dataset data/combined_python_pairs.json
"""
import sys
import json
import re
import argparse
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.relation_engine import classify_pair


# ---------- Tree-sitter setup ----------
PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)


# ---------- Diff parsing helpers ----------

def extract_code_and_context(diff_path: str):
    """
    Reads a unified .diff file and returns:
      - added_code: all '+' (added) lines, concatenated, for AST parsing
      - removed_code: all '-' (removed) lines, concatenated, for AST parsing
      - hunk_contexts: the function/class signature git shows after each @@ header
                        (git includes nearby enclosing-function context automatically)

    Parsing removed_code lets us catch a case added-lines-only parsing
    can NEVER see: a PR that deletes or renames a function entirely
    (rather than editing its body) — that only shows up in '-' lines.

    NOTE: a version of this also scanned every line in the hunk BODY
    (not just the header) for module-level constant/collection
    assignments like '__all__ = [', to catch cases where that
    assignment line itself was unchanged context rather than an added/
    removed line. That was REVERTED — see relation_engine.py's
    extract_symbol_name_from_signature docstring for why (it hurt
    precision more than it helped recall on full-dataset evaluation).
    """
    text = Path(diff_path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    added_lines = []
    removed_lines = []
    hunk_contexts = []

    hunk_header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@\s*(.*)$")

    for line in lines:
        header_match = hunk_header_re.match(line)
        if header_match:
            context = header_match.group(1).strip()
            if context:
                hunk_contexts.append(context)
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added_lines.append(line[1:])  # strip the leading '+'
        elif line.startswith("-"):
            removed_lines.append(line[1:])  # strip the leading '-'

    added_code = "\n".join(added_lines)
    removed_code = "\n".join(removed_lines)
    return added_code, removed_code, hunk_contexts


# ---------- Tree-sitter extraction ----------

def extract_symbols(code: str):
    """
    Parses `code` with Tree-sitter and walks the AST to pull out:
      - function definitions
      - class definitions
      - function/method calls
      - imports
    """
    if not code.strip():
        return {"functions": [], "classes": [], "calls": [], "call_leaf_names": [], "imports": []}

    tree = parser.parse(bytes(code, "utf-8"))
    root = tree.root_node

    functions, classes, calls, call_leaf_names, imports = [], [], [], [], []

    def walk(node):
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                functions.append(name_node.text.decode("utf-8"))
        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                classes.append(name_node.text.decode("utf-8"))
        elif node.type == "call":
            fn_node = node.child_by_field_name("function")
            if fn_node:
                full_call_text = fn_node.text.decode("utf-8")
                calls.append(full_call_text)
                # Also record just the last piece (e.g. "auth.validate" -> "validate")
                # so a method call can be matched against a bare function/method
                # definition name found elsewhere. This is what actually lets us
                # notice that PR B calling "auth.validate()" touches the same
                # "validate" that PR A just defined.
                leaf_name = full_call_text.split(".")[-1]
                call_leaf_names.append(leaf_name)
        elif node.type in ("import_statement", "import_from_statement"):
            imports.append(node.text.decode("utf-8").strip())

        for child in node.children:
            walk(child)

    walk(root)

    return {
        "functions": sorted(set(functions)),
        "classes": sorted(set(classes)),
        "calls": sorted(set(calls)),
        "call_leaf_names": sorted(set(call_leaf_names)),
        "imports": sorted(set(imports)),
    }


def analyze_pr_diff(diff_path: str, label: str):
    print(f"\n  --- {label}: {diff_path} ---")
    added_code, removed_code, contexts = extract_code_and_context(diff_path)

    if contexts:
        print(f"  Enclosing function/class context (from diff hunk headers):")
        for c in contexts[:5]:
            print(f"    - {c}")
    else:
        print("  (no enclosing-function context found in diff headers)")

    symbols_added = extract_symbols(added_code)
    symbols_removed = extract_symbols(removed_code)

    print(f"  Functions defined/touched : {symbols_added['functions'] or '(none found)'}")
    print(f"  Classes defined/touched   : {symbols_added['classes'] or '(none found)'}")
    print(f"  Function calls found      : {symbols_added['calls'] or '(none found)'}")
    print(f"  Imports found             : {symbols_added['imports'] or '(none found)'}")

    removed_defs = (set(symbols_removed["functions"]) | set(symbols_removed["classes"])) - \
                   (set(symbols_added["functions"]) | set(symbols_added["classes"]))
    if removed_defs:
        print(f"  Functions/classes DELETED (in removed lines, not re-added) : {sorted(removed_defs)}")

    return symbols_added, symbols_removed, contexts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="Path to combined_python_pairs.json")
    args = ap.parse_args()

    with open(args.dataset, "r", encoding="utf-8") as f:
        data = json.load(f)

    pairs = data["pairs"]
    conflict_example = next((p for p in pairs if p["label"] == "CONFLICT"), None)
    dependency_example = next((p for p in pairs if p["label"] == "DEPENDENCY"), None)

    for example, label in [(conflict_example, "CONFLICT"), (dependency_example, "DEPENDENCY")]:
        if example is None:
            print(f"\nNo {label} example found in dataset — skipping.")
            continue

        print("\n" + "=" * 70)
        print(f"EXAMPLE LABEL: {label}   (pool: {example.get('pool', '?')})")
        print(f"PR A: {example['pr_a']}   |   PR B: {example['pr_b']}")
        print("=" * 70)

        symbols_a, removed_a, contexts_a = analyze_pr_diff(example["diff_a_path"], f"PR {example['pr_a']}")
        symbols_b, removed_b, contexts_b = analyze_pr_diff(example["diff_b_path"], f"PR {example['pr_b']}")

        result = classify_pair(symbols_a, contexts_a, symbols_b, contexts_b,
                                removed_symbols_a=removed_a, removed_symbols_b=removed_b)
        print(f"\n  >>> Relation engine result:")
        print(f"      Predicted label: {result.label}   (evidence: {sorted(result.conflict_evidence or result.dependency_evidence)})")
        print(f"      Ground-truth label: {label}")


if __name__ == "__main__":
    main()