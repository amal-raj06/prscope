"""
PRScope — eval/metrics.py
---------------------------
Shared per-class precision/recall/F1 computation from a confusion matrix.
Extracted out of run_relation_engine.py so both the relation engine's own
eval AND the baseline comparisons in eval/compare_baselines.py use the
exact same math — one source of truth, no risk of the two drifting apart
and producing numbers that aren't directly comparable.

confusion[actual][predicted] = count, a defaultdict(lambda: defaultdict(int))
"""

LABELS = ["CONFLICT", "DEPENDENCY", "INDEPENDENT"]


def compute_per_class_metrics(confusion) -> dict:
    """
    Returns {label: {"precision": .., "recall": .., "f1": .., "support": ..}}
    plus a special "_overall" key with {"accuracy": .., "total": ..}.
    """
    results = {}
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

        results[label] = {"precision": precision, "recall": recall, "f1": f1, "support": support}
        overall_correct += tp
        overall_total += support

    overall_acc = overall_correct / overall_total if overall_total > 0 else 0.0
    results["_overall"] = {"accuracy": overall_acc, "total": overall_total}
    return results


def print_per_class_metrics(confusion, total_pairs, n_errors, title="PER-CLASS METRICS"):
    metrics = compute_per_class_metrics(confusion)

    print("=" * 70)
    print(f"{title}  (total pairs: {total_pairs}, parse errors: {n_errors})")
    print("=" * 70)
    print(f"{'Class':<13}{'Precision':<12}{'Recall':<12}{'F1':<10}{'Support'}")

    for label in LABELS:
        m = metrics[label]
        print(f"{label:<13}{m['precision']:<12.3f}{m['recall']:<12.3f}{m['f1']:<10.3f}{m['support']}")

    independent_support = metrics["INDEPENDENT"]["support"]
    total = metrics["_overall"]["total"]
    print(f"\nOverall accuracy: {metrics['_overall']['accuracy']:.3f}  "
          f"(shown for reference only — per-class numbers above are what matter "
          f"given class imbalance: {independent_support} of {total} pairs are INDEPENDENT)")

    return metrics