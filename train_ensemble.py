"""
PRScope - Asymmetric Rule-Veto Ensemble
---------------------------------------
Prioritizes the high-precision deterministic AST rules.
Uses LightGBM purely as a fallback to catch hidden conflicts 
when the rule engine defaults to INDEPENDENT.
"""

import argparse
import json
import numpy as np
from pathlib import Path
from collections import defaultdict

import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder

from tree_sitter_poc import extract_code_and_context, extract_symbols
from engine.relation_engine import (
    get_defined_symbols,
    get_modified_symbols,
    get_called_symbols,
    get_removed_definitions,
    classify_pair
)
from eval.metrics import compute_per_class_metrics, LABELS

def resolve_diff_path(raw_path: str, pools_root: Path) -> Path:
    normalized = raw_path.replace("\\", "/")
    rel_path = normalized.split("pools/")[-1] if "pools/" in normalized else normalized
    return pools_root / rel_path

def extract_pair_features(pair: dict, pools_root: Path) -> dict:
    diff_a_raw = pair.get("diff_a_path", "")
    diff_b_raw = pair.get("diff_b_path", "")
    path_a = resolve_diff_path(diff_a_raw, pools_root)
    path_b = resolve_diff_path(diff_b_raw, pools_root)

    added_a, removed_a_code, ctx_a = ("", "", [])
    added_b, removed_b_code, ctx_b = ("", "", [])

    if path_a.exists(): added_a, removed_a_code, ctx_a = extract_code_and_context(str(path_a))
    if path_b.exists(): added_b, removed_b_code, ctx_b = extract_code_and_context(str(path_b))

    sym_added_a = extract_symbols(added_a)
    sym_removed_a = extract_symbols(removed_a_code)
    sym_added_b = extract_symbols(added_b)
    sym_removed_b = extract_symbols(removed_b_code)

    def_a = get_defined_symbols(sym_added_a)
    mod_a = get_modified_symbols(ctx_a)
    call_a = get_called_symbols(sym_added_a)
    rem_def_a = get_removed_definitions(sym_added_a, sym_removed_a)
    imports_a = set(sym_added_a.get("imports", []))

    def_b = get_defined_symbols(sym_added_b)
    mod_b = get_modified_symbols(ctx_b)
    call_b = get_called_symbols(sym_added_b)
    rem_def_b = get_removed_definitions(sym_added_b, sym_removed_b)
    imports_b = set(sym_added_b.get("imports", []))

    rule_result = classify_pair(sym_added_a, ctx_a, sym_added_b, ctx_b, sym_removed_a, sym_removed_b)
    
    files_a = set(line[6:] for line in (path_a.read_text(encoding="utf-8", errors="ignore").splitlines() if path_a.exists() else []) if line.startswith("+++ b/"))
    files_b = set(line[6:] for line in (path_b.read_text(encoding="utf-8", errors="ignore").splitlines() if path_b.exists() else []) if line.startswith("+++ b/"))

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
        "same_file_touch": 1.0 if (files_a & files_b) else 0.0,
    }
    
    return features, rule_result.label

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--pools-dir", required=True)
    args = parser.parse_args()

    pools_root = Path(args.pools_dir)
    with open(args.dataset, "r", encoding="utf-8") as f:
        pairs = json.load(f)["pairs"]

    print("Extracting features and running deterministic engine...")
    features, rule_preds, labels = [], [], []
    for p in pairs:
        feats, rule_label = extract_pair_features(p, pools_root)
        features.append(feats)
        rule_preds.append(rule_label)
        labels.append(p["label"])

    X = np.array([[row[k] for k in features[0].keys()] for row in features])
    le = LabelEncoder().fit(LABELS)
    y = le.transform(labels)

    confusion = defaultdict(lambda: defaultdict(int))
    skf = StratifiedKFold(n_splits=4, shuffle=True, random_state=42)

    print("Evaluating Asymmetric Rule-Veto Ensemble...")
    for train_idx, test_idx in skf.split(X, y):
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        # Train LightGBM on the fold
        model = lgb.LGBMClassifier(objective="multiclass", num_class=3, random_state=42, n_estimators=100, learning_rate=0.05, verbose=-1)
        model.fit(X_train, y_train)
        
        # Get ML predictions for the test set
        lgbm_preds = model.predict(X_test)
        lgbm_pred_labels = le.inverse_transform(lgbm_preds)

        # Apply the Veto Logic
        for i, test_index in enumerate(test_idx):
            actual = labels[test_index]
            rule_pred = rule_preds[test_index]
            lgbm_pred = lgbm_pred_labels[i]

            # If the rule engine found a definitive relationship, trust it completely.
            # Otherwise, fall back to what the ML model thinks.
            final_pred = rule_pred if rule_pred != "INDEPENDENT" else lgbm_pred
            
            confusion[actual][final_pred] += 1

    metrics = compute_per_class_metrics(confusion)
    
    print("\nASYMMETRIC ENSEMBLE RESULTS (Rules + LightGBM Fallback)")
    print(f"{'Class':<13}{'Precision':<12}{'Recall':<12}{'F1':<10}{'Support'}")
    for label in LABELS:
        print(f"{label:<13}{metrics[label]['precision']:<12.3f}{metrics[label]['recall']:<12.3f}{metrics[label]['f1']:<10.3f}{metrics[label]['support']}")

if __name__ == "__main__":
    main()