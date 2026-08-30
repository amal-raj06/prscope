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
import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp
import tree_sitter_java as tsjava
from tree_sitter import Language, Parser
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.relation_engine import classify_pair

def get_parser(extension: str) -> Parser:
    """Dynamically loads the correct Tree-sitter grammar based on target file extension."""
    if extension == '.c':
        lang = Language(tsc.language())
    elif extension in ('.cpp', '.cc', '.h', '.hpp'):
        lang = Language(tscpp.language())
    elif extension == '.java':
        lang = Language(tsjava.language())
    else:
        lang = Language(tspython.language()) # Default to Python
    return Parser(lang)



# ---------- Diff parsing helpers ----------

def extract_code_and_context(diff_path: str):
    text = Path(diff_path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    added_lines, removed_lines, hunk_contexts = [], [], []
    hunk_header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@\s*(.*)$")
    target_ext = ".py"  # Default

    for line in lines:
        if line.startswith("+++ b/"):
            target_ext = Path(line[6:].strip()).suffix.lower()
            continue
        header_match = hunk_header_re.match(line)
        if header_match:
            context = header_match.group(1).strip()
            if context: hunk_contexts.append(context)
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added_lines.append(line[1:])
        elif line.startswith("-"):
            removed_lines.append(line[1:])

    added_code = "\n".join(added_lines)
    removed_code = "\n".join(removed_lines)
    return added_code, removed_code, hunk_contexts, target_ext


# ---------- Tree-sitter extraction ----------

def extract_symbols(code: str, parser: Parser):
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
        # Look for both Python and Java/C++ naming conventions
        if node.type in ("function_definition", "method_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node:
                functions.append(name_node.text.decode("utf-8"))
                
        elif node.type in ("class_definition", "class_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node:
                classes.append(name_node.text.decode("utf-8"))
                
        elif node.type in ("call", "method_invocation", "call_expression"):
            # Python uses 'function' field, Java uses 'name' field
            fn_node = node.child_by_field_name("function") or node.child_by_field_name("name")
            if fn_node:
                full_call_text = fn_node.text.decode("utf-8")
                calls.append(full_call_text)
                leaf_name = full_call_text.split(".")[-1]
                call_leaf_names.append(leaf_name)
                
        elif node.type in ("import_statement", "import_from_statement", "import_declaration"):
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
    added_code, removed_code, contexts, target_ext = extract_code_and_context(diff_path)

    parser = get_parser(target_ext)

    if contexts:
        print(f"  Enclosing function/class context (from diff hunk headers):")
        for c in contexts[:5]:
            print(f"    - {c}")
    else:
        print("  (no enclosing-function context found in diff headers)")

    symbols_added = extract_symbols(added_code, parser)
    symbols_removed = extract_symbols(removed_code, parser)

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