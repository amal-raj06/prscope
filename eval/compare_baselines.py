"""
PRScope — eval/compare_baselines.py
--------------------------------------
Runs THREE approaches across the full labeled dataset and prints their
per-class metrics side by side:
  1. majority_baseline       — always predicts INDEPENDENT
  2. git_line_overlap_baseline — mimics real Git line-based conflict detection
  3. relation_engine.classify_pair — our deterministic structural engine

This is the concrete evidence for the poster/pitch claim that PRScope
catches relationships naive/existing approaches miss — not an assertion,
a measured comparison on the same 198 real pairs.

Usage:
    python eval/compare_baselines.py --dataset data/combined_python_pairs.json
"""

import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.relation_engine import classify_pair
from data.scripts.tree_sitter_poc import extract_code_and_context, extract_symbols
from eval.metrics import print_per_class_metrics
from eval.baselines import majority_baseline, git_line_overlap_baseline


def analyze_diff(diff_path: str):
    added_code, removed_code, contexts = extract_code_and_context(diff_path)
    symbols_added = extract_symbols(added_code)
    symbols_removed = extract_symbols(removed_code)
    return symbols_added, symbols_removed, contexts


def run_comparison(dataset_path: str):
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    pairs = data["pairs"]

    confusion_majority = defaultdict(lambda: defaultdict(int))
    confusion_git = defaultdict(lambda: defaultdict(int))
    confusion_engine = defaultdict(lambda: defaultdict(int))
    n_errors = 0

    for pair in pairs:
        actual = pair["label"]
        diff_a, diff_b = pair["diff_a_path"], pair["diff_b_path"]

        # Baseline 1: majority class
        confusion_majority[actual][majority_baseline()] += 1

        # Baseline 2: git line-overlap
        confusion_git[actual][git_line_overlap_baseline(diff_a, diff_b)] += 1

        # Our engine
        try:
            symbols_a, removed_a, contexts_a = analyze_diff(diff_a)
            symbols_b, removed_b, contexts_b = analyze_diff(diff_b)
            result = classify_pair(symbols_a, contexts_a, symbols_b, contexts_b,
                                    removed_symbols_a=removed_a, removed_symbols_b=removed_b)
            confusion_engine[actual][result.label] += 1
        except Exception:
            n_errors += 1

    return confusion_majority, confusion_git, confusion_engine, len(pairs), n_errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    args = ap.parse_args()

    confusion_majority, confusion_git, confusion_engine, total, n_errors = run_comparison(args.dataset)

    print_per_class_metrics(confusion_majority, total, 0,
                             title="BASELINE 1: Majority class (always INDEPENDENT)")
    print()
    print_per_class_metrics(confusion_git, total, 0,
                             title="BASELINE 2: Git line-overlap (mimics real Git conflict detection)")
    print()
    print_per_class_metrics(confusion_engine, total, n_errors,
                             title="PRScope relation engine (this project)")


if __name__ == "__main__":
    main()