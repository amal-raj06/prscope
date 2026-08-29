"""
PRScope - LightGBM Refinement Layer & Evaluation Pipeline
---------------------------------------------------------
Implements the optional LightGBM classification layer on top of the
deterministic structural features for PRScope (DevJams'26, team CommitZero).

Usage:
    python train_lgbm.py --dataset combined_python_pairs.json --pools-dir .
"""

import os
import json
import argparse
import numpy as np
from collections import defaultdict
from pathlib import Path

import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder

from tree_sitter_poc import (
    extract_code_and_context,
    extract_symbols
)
# Change these lines in train_lgbm.py:
from engine.relation_engine import (
    get_defined_symbols,
    get_modified_symbols,
    get_called_symbols,
    get_removed_definitions,
    classify_pair
)
from eval.metrics import compute_per_class_metrics, LABELS


def resolve_diff_path(raw_path: str, pools_root: Path) -> Path:
    """
    Rewrites Windows backslashes and BulkPR-Bench prefixes to match
    wherever the pools folder is actually placed locally.
    """
    # Normalize path separators
    normalized = raw_path.replace("\\", "/")
    # Extract relative part after 'data/pools/' or 'pools/'
    if "pools/" in normalized:
        parts = normalized.split("pools/")
        rel_path = parts[-1]
    else:
        rel_path = normalized

    return pools_root / rel_path


def extract_pair_features(pair: dict, pools_root: Path) -> dict:
    """
    Extracts structural numeric features for a single PR pair.
    """
    diff_a_raw = pair.get("diff_a_path", "")
    diff_b_raw = pair.get("diff_b_path", "")

    path_a = resolve_diff_path(diff_a_raw, pools_root)
    path_b = resolve_diff_path(diff_b_raw, pools_root)

    # Fallback or empty defaults if files don't exist
    added_a, removed_a_code, ctx_a = "", "", []
    added_b, removed_b_code, ctx_b = "", "", []

    if path_a.exists():
        added_a, removed_a_code, ctx_a = extract_code_and_context(str(path_a))
    if path_b.exists():
        added_b, removed_b_code, ctx_b = extract_code_and_context(str(path_b))

    sym_added_a = extract_symbols(added_a)
    sym_removed_a = extract_symbols(removed_a_code)
    sym_added_b = extract_symbols(added_b)
    sym_removed_b = extract_symbols(removed_b_code)

    def_a = get_defined_symbols(sym_added_a)
    mod_a = get_modified_symbols(ctx_a)
    call_a = get_called_symbols(sym_added_a)
    imports_a = set(sym_added_a.get("imports", []))
    rem_def_a = get_removed_definitions(sym_added_a, sym_removed_a)

    def_b = get_defined_symbols(sym_added_b)
    mod_b = get_modified_symbols(ctx_b)
    call_b = get_called_symbols(sym_added_b)
    imports_b = set(sym_added_b.get("imports", []))
    rem_def_b = get_removed_definitions(sym_added_b, sym_removed_b)

    # Run deterministic rule engine to include its prediction as a feature
    rule_result = classify_pair(
        sym_added_a, ctx_a, sym_added_b, ctx_b,
        removed_symbols_a=sym_removed_a, removed_symbols_b=sym_removed_b,
        diff_a_path=str(path_a) if path_a.exists() else None,
        diff_b_path=str(path_b) if path_b.exists() else None
    )
    rule_label_map = {"CONFLICT": 0, "DEPENDENCY": 1, "INDEPENDENT": 2}
    rule_pred_encoded = rule_label_map.get(rule_result.label, 2)

    # File touch overlap
    files_a = set()
    files_b = set()
    if path_a.exists():
        for line in path_a.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("+++ b/"):
                files_a.add(line[6:])
    if path_b.exists():
        for line in path_b.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("+++ b/"):
                files_b.add(line[6:])
    same_file_touch = 1.0 if (files_a & files_b) else 0.0

    features = {
        "dep_overlap_a_b": len(def_a & call_b),
        "dep_overlap_b_a": len(def_b & call_a),
        "mod_overlap_a_b": len(mod_a & call_b),
        "mod_overlap_b_a": len(mod_b & call_a),
        "mod_both_overlap": len(mod_a & mod_b),
        "rem_overlap_a_b": len(rem_def_a & call_b),
        "rem_overlap_b_a": len(rem_def_b & call_a),
        "import_overlap": len(imports_a & imports_b),
        
        "len_funcs_a": len(sym_added_a["functions"]),
        "len_funcs_b": len(sym_added_b["functions"]),
        "len_classes_a": len(sym_added_a["classes"]),
        "len_classes_b": len(sym_added_b["classes"]),
        "len_calls_a": len(sym_added_a["calls"]),
        "len_calls_b": len(sym_added_b["calls"]),
        "len_imports_a": len(sym_added_a["imports"]),
        "len_imports_b": len(sym_added_b["imports"]),

        "same_file_touch": same_file_touch,
        "rule_engine_prediction": rule_pred_encoded,
        
        "conflict_evidence_size": len(rule_result.conflict_evidence),
        "dependency_evidence_size": len(rule_result.dependency_evidence),
    }

    return features


def main():
    parser = argparse.ArgumentParser(description="Train and evaluate LightGBM model for PRScope")
    parser.add_argument("--dataset", required=True, help="Path to combined_python_pairs.json")
    parser.add_argument("--pools-dir", required=True, help="Path to parent directory containing the pools folder")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    pools_root = Path(args.pools_dir)

    print(f"Loading dataset from {dataset_path}...")
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pairs = data["pairs"]
    print(f"Total pairs in dataset: {len(pairs)}")

    # 1. Feature Extraction verification & build
    print("Extracting features across all pairs...")
    feature_rows = []
    labels = []

    for i, pair in enumerate(pairs):
        feats = extract_pair_features(pair, pools_root)
        feature_rows.append(feats)
        labels.append(pair["label"])

    # Convert to feature matrix X and label array y
    feature_names = list(feature_rows[0].keys())
    X = np.array([[row[f] for f in feature_names] for row in feature_rows])
    
    le = LabelEncoder()
    le.fit(LABELS)  # ensures fixed mapping: CONFLICT=0, DEPENDENCY=1, INDEPENDENT=2
    y = le.transform(labels)

    print(f"Feature matrix shape: {X.shape}")
    assert not np.isnan(X).any(), "Feature matrix contains NaNs!"

    # 2. 4-Fold Stratified Cross-Validation
    RANDOM_STATE = 42
    n_splits = 4
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)

    print(f"Running {n_splits}-fold Stratified Cross-Validation (random_state={RANDOM_STATE})...")

    confusion = defaultdict(lambda: defaultdict(int))
    feature_importances = np.zeros(len(feature_names))

    fold_idx = 1
    for train_idx, test_idx in skf.split(X, y):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        # Check fold distribution for DEPENDENCY (class index 1)
        train_dep_count = np.sum(y_train == 1)
        test_dep_count = np.sum(y_test == 1)
        print(f"  [Fold {fold_idx}] Train size: {len(X_train)} (Dependency: {train_dep_count}), "
              f"Test size: {len(X_test)} (Dependency: {test_dep_count})")

        if train_dep_count == 0 or test_dep_count == 0:
            print(f"  WARNING: Fold {fold_idx} has zero DEPENDENCY examples in train or test!")

        # Train LightGBM multi-class classifier
        model = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=3,
            random_state=RANDOM_STATE,
            n_estimators=100,
            learning_rate=0.05,
            verbose=-1
        )
        model.fit(X_train, y_train)

        # Accumulate feature importances
        feature_importances += model.feature_importances_ / n_splits

        # Predict on held-out test fold
        y_pred = model.predict(X_test)

        # Accumulate into global confusion matrix
        for actual_numeric, pred_numeric in zip(y_test, y_pred):
            actual_str = le.inverse_transform([actual_numeric])[0]
            pred_str = le.inverse_transform([pred_numeric])[0]
            confusion[actual_str][pred_str] += 1

        fold_idx += 1

    # 3. Evaluate Out-of-Fold Predictions via metrics.py
    total_pairs = len(pairs)
    metrics_results = compute_per_class_metrics(confusion)

    print("\n" + "=" * 70)
    print("LIGHTGBM OUT-OF-FOLD EVALUATION RESULTS")
    print("=" * 70)
    print(f"{'Class':<13}{'Precision':<12}{'Recall':<12}{'F1':<10}{'Support'}")

    for label in LABELS:
        m = metrics_results[label]
        print(f"{label:<13}{m['precision']:<12.3f}{m['recall']:<12.3f}{m['f1']:<10.3f}{m['support']}")

    print(f"\nOverall accuracy: {metrics_results['_overall']['accuracy']:.3f}")

    # 4. Print Feature Importances
    print("\n" + "=" * 70)
    print("TOP FEATURE IMPORTANCES (LightGBM)")
    print("=" * 70)
    sorted_fi_idx = np.argsort(feature_importances)[::-1]
    for idx in sorted_fi_idx:
        print(f"  {feature_names[idx]:<30}: {feature_importances[idx]:.2f}")

    print("\nExecution complete.")


if __name__ == "__main__":
    main()