"""
PRScope — eval/run_relation_engine.py
---------------------------------------
Runs the deterministic relation engine (engine/relation_engine.py) across
the FULL labeled dataset (data/combined_python_pairs.json, all 198 pairs),
not just the 2 hand-picked sanity-check examples used during POC dev.

Reports PER-CLASS precision/recall/F1 for CONFLICT / DEPENDENCY /
INDEPENDENT — never overall accuracy alone, since the dataset is
imbalanced (150 INDEPENDENT / 32 CONFLICT / 16 DEPENDENCY) and a naive
"always predict INDEPENDENT" baseline would score ~76% accuracy while
being useless.

Also prints every MISCLASSIFIED pair with its predicted vs. actual label
and the evidence the engine used, so you can eyeball failure patterns
before deciding whether to refine the rule or move on to ML.

Usage:
    python eval/run_relation_engine.py --dataset data/combined_python_pairs.json
"""

import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict

# repo root = parent of this file's folder (eval/ -> prscope/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.relation_engine import classify_pair
# Re-uses the exact same diff-parsing + Tree-sitter extraction functions
# your POC already validated — no reimplementation, no drift.
from data.scripts.tree_sitter_poc import extract_code_and_context, extract_symbols


LABELS = ["CONFLICT", "DEPENDENCY", "INDEPENDENT"]


def analyze_diff(diff_path: str):
    added_code, removed_code, contexts = extract_code_and_context(diff_path)
    symbols_added = extract_symbols(added_code)
    symbols_removed = extract_symbols(removed_code)
    return symbols_added, symbols_removed, contexts


def evaluate(dataset_path: str):
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    pairs = data["pairs"]

    # confusion[actual][predicted] = count
    confusion = defaultdict(lambda: defaultdict(int))
    errors = []          # pairs that failed to parse/classify at all
    misclassified = []   # pairs that parsed fine but got the wrong label

    for i, pair in enumerate(pairs):
        try:
            symbols_a, removed_a, contexts_a = analyze_diff(pair["diff_a_path"])
            symbols_b, removed_b, contexts_b = analyze_diff(pair["diff_b_path"])
            result = classify_pair(symbols_a, contexts_a, symbols_b, contexts_b,
                                    removed_symbols_a=removed_a, removed_symbols_b=removed_b)
        except Exception as e:
            errors.append({"index": i, "pool": pair.get("pool"),
                            "pr_a": pair["pr_a"], "pr_b": pair["pr_b"], "error": str(e)})
            continue

        actual = pair["label"]
        predicted = result.label
        confusion[actual][predicted] += 1

        if predicted != actual:
            evidence = sorted(result.conflict_evidence or result.dependency_evidence)
            misclassified.append({
                "pool": pair.get("pool"), "pr_a": pair["pr_a"], "pr_b": pair["pr_b"],
                "actual": actual, "predicted": predicted, "evidence": evidence,
            })

    return confusion, errors, misclassified, len(pairs)


def print_per_class_metrics(confusion, total_pairs, n_errors):
    print("=" * 70)
    print(f"PER-CLASS METRICS  (total pairs: {total_pairs}, parse errors: {n_errors})")
    print("=" * 70)
    print(f"{'Class':<13}{'Precision':<12}{'Recall':<12}{'F1':<10}{'Support'}")

    overall_correct = 0
    overall_total = 0

    for label in LABELS:
        tp = confusion[label][label]
        fn = sum(confusion[label][pred] for pred in LABELS if pred != label)
        fp = sum(confusion[actual][label] for actual in LABELS if actual != label)
        support = tp + fn

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        print(f"{label:<13}{precision:<12.3f}{recall:<12.3f}{f1:<10.3f}{support}")

        overall_correct += tp
        overall_total += support

    overall_acc = overall_correct / overall_total if overall_total > 0 else 0.0
    print(f"\nOverall accuracy: {overall_acc:.3f}  "
          f"(shown for reference only — per-class numbers above are what matter "
          f"given class imbalance: {sum(confusion[l][l2] for l in LABELS for l2 in LABELS if l=='INDEPENDENT')} "
          f"of {overall_total} pairs are INDEPENDENT)")


def print_misclassified(misclassified, max_show=20):
    print("\n" + "=" * 70)
    print(f"MISCLASSIFIED PAIRS ({len(misclassified)} total, showing up to {max_show})")
    print("=" * 70)
    for m in misclassified[:max_show]:
        print(f"  [{m['pool']}] {m['pr_a']} vs {m['pr_b']}  |  "
              f"actual={m['actual']}  predicted={m['predicted']}  "
              f"evidence={m['evidence'] or '(none)'}")


def print_errors(errors, max_show=10):
    if not errors:
        return
    print("\n" + "=" * 70)
    print(f"PARSE/CLASSIFY ERRORS ({len(errors)} total, showing up to {max_show})")
    print("=" * 70)
    for e in errors[:max_show]:
        print(f"  [{e['pool']}] {e['pr_a']} vs {e['pr_b']}  |  error: {e['error']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="Path to combined_python_pairs.json")
    ap.add_argument("--show-misclassified", type=int, default=20,
                     help="Max number of misclassified pairs to print (default 20)")
    args = ap.parse_args()

    confusion, errors, misclassified, total_pairs = evaluate(args.dataset)
    print_per_class_metrics(confusion, total_pairs, len(errors))
    print_misclassified(misclassified, max_show=args.show_misclassified)
    print_errors(errors)


if __name__ == "__main__":
    main()