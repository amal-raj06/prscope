"""
PRScope — eval/debug_pair.py
------------------------------
Diagnostic tool: given a pool + two PR ids from combined_python_pairs.json,
prints the FULL raw diff content and the full extracted-symbol breakdown
for both PRs, so you can see exactly why the relation engine did or
didn't find overlap — instead of guessing from the summary metrics.

Usage:
    python eval/debug_pair.py --dataset data/combined_python_pairs.json --pool attrs --pr-a PR-07 --pr-b PR-04
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.relation_engine import classify_pair
from data.scripts.tree_sitter_poc import extract_code_and_context, extract_symbols


def dump_pr(diff_path: str, label: str):
    print(f"\n{'=' * 70}\nRAW DIFF: {label}  ({diff_path})\n{'=' * 70}")
    raw = Path(diff_path).read_text(encoding="utf-8", errors="ignore")
    print(raw)

    added_code, removed_code, contexts = extract_code_and_context(diff_path)
    symbols_added = extract_symbols(added_code)
    symbols_removed = extract_symbols(removed_code)

    print(f"\n--- Extracted from ADDED ('+') lines ---")
    print(f"  functions: {symbols_added['functions']}")
    print(f"  classes:   {symbols_added['classes']}")
    print(f"  calls:     {symbols_added['calls']}")
    print(f"  call_leaf_names: {symbols_added['call_leaf_names']}")
    print(f"  imports:   {symbols_added['imports']}")

    print(f"\n--- Extracted from REMOVED ('-') lines ---")
    print(f"  functions: {symbols_removed['functions']}")
    print(f"  classes:   {symbols_removed['classes']}")
    print(f"  calls:     {symbols_removed['calls']}")

    print(f"\n--- Hunk-header enclosing context ---")
    print(f"  {contexts if contexts else '(none found)'}")

    return symbols_added, symbols_removed, contexts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--pool", required=True)
    ap.add_argument("--pr-a", required=True)
    ap.add_argument("--pr-b", required=True)
    args = ap.parse_args()

    with open(args.dataset, "r", encoding="utf-8") as f:
        data = json.load(f)

    pair = next((p for p in data["pairs"]
                 if p.get("pool") == args.pool and p["pr_a"] == args.pr_a and p["pr_b"] == args.pr_b), None)
    if pair is None:
        print(f"No pair found for pool={args.pool}, pr_a={args.pr_a}, pr_b={args.pr_b}")
        return

    print(f"Ground-truth label: {pair['label']}   (source_relation_type: {pair.get('source_relation_type')})")

    symbols_a, removed_a, contexts_a = dump_pr(pair["diff_a_path"], f"PR {args.pr_a} (A)")
    symbols_b, removed_b, contexts_b = dump_pr(pair["diff_b_path"], f"PR {args.pr_b} (B)")

    result = classify_pair(symbols_a, contexts_a, symbols_b, contexts_b,
                            removed_symbols_a=removed_a, removed_symbols_b=removed_b)
    print(f"\n{'=' * 70}\nPredicted: {result.label}   Ground truth: {pair['label']}\n{'=' * 70}")


if __name__ == "__main__":
    main()