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

def extract_added_code_and_context(diff_path: str):
    """
    Reads a unified .diff file and returns:
      - reconstructed_code: all '+' (added) lines, concatenated, for AST parsing
      - hunk_contexts: the function/class signature git shows after each @@ header
                        (git includes nearby enclosing-function context automatically)
    """
    text = Path(diff_path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    added_lines = []
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

    reconstructed_code = "\n".join(added_lines)
    return reconstructed_code, hunk_contexts


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
    code, contexts = extract_added_code_and_context(diff_path)

    if contexts:
        print(f"  Enclosing function/class context (from diff hunk headers):")
        for c in contexts[:5]:
            print(f"    - {c}")
    else:
        print("  (no enclosing-function context found in diff headers)")

    symbols = extract_symbols(code)
    print(f"  Functions defined/touched : {symbols['functions'] or '(none found)'}")
    print(f"  Classes defined/touched   : {symbols['classes'] or '(none found)'}")
    print(f"  Function calls found      : {symbols['calls'] or '(none found)'}")
    print(f"  Imports found             : {symbols['imports'] or '(none found)'}")

    return symbols, contexts


def find_shared_symbols(symbols_a, symbols_b, contexts_a, contexts_b):
    """
    Very simple overlap check: does PR A touch/define something that
    PR B also touches or calls? This is the seed of the relation engine
    we'll build in the next step — not the final logic yet.
    """
    a_all = set(symbols_a["functions"]) | set(symbols_a["classes"])
    b_all = set(symbols_b["functions"]) | set(symbols_b["classes"])
    b_calls = set(symbols_b["call_leaf_names"])
    a_calls = set(symbols_a["call_leaf_names"])

    a_defines_b_calls = a_all & b_calls
    b_defines_a_calls = b_all & a_calls
    shared_context = set(contexts_a) & set(contexts_b)

    return {
        "a_defines_that_b_calls": sorted(a_defines_b_calls),
        "b_defines_that_a_calls": sorted(b_defines_a_calls),
        "shared_diff_context_lines": sorted(shared_context),
    }





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

        symbols_a, contexts_a = analyze_pr_diff(example["diff_a_path"], f"PR {example['pr_a']}")
        symbols_b, contexts_b = analyze_pr_diff(example["diff_b_path"], f"PR {example['pr_b']}")

        
        result = classify_pair(symbols_a, contexts_a, symbols_b, contexts_b)
        print(f"\n  >>> Relation engine result:")
        print(f"      Predicted label: {result.label}   (evidence: {sorted(result.conflict_evidence or result.dependency_evidence)})")
        print(f"      Ground-truth label: {label}")

if __name__ == "__main__":
    main()