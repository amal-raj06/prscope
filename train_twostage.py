"""
PRScope - Two-Stage Cascaded ML Pipeline
----------------------------------------
Stage 1: Classifies pairs as INDEPENDENT vs. RELATED
Stage 2: If RELATED, classifies as CONFLICT vs. DEPENDENCY
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
    # (Same feature extraction logic as before)
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
    rule_pred_encoded = {"CONFLICT": 0, "DEPENDENCY": 1, "INDEPENDENT": 2}.get(rule_result.label, 2)

    files_a = set(line[6:] for line in (path_a.read_text(encoding="utf-8", errors="ignore").splitlines() if path_a.exists() else []) if line.startswith("+++ b/"))
    files_b = set(line[6:] for line in (path_b.read_text(encoding="utf-8", errors="ignore").splitlines() if path_b.exists() else []) if line.startswith("+++ b/"))

    return {
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
        "rule_engine_prediction": rule_pred_encoded,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--pools-dir", required=True)
    args = parser.parse_args()

    pools_root = Path(args.pools_dir)
    with open(args.dataset, "r", encoding="utf-8") as f:
        pairs = json.load(f)["pairs"]

    print("Extracting features...")
    features, labels = [], []
    for p in pairs:
        features.append(extract_pair_features(p, pools_root))
        labels.append(p["label"])

    X = np.array([[row[k] for k in features[0].keys()] for row in features])
    le = LabelEncoder().fit(LABELS) # CONFLICT=0, DEPENDENCY=1, INDEPENDENT=2
    y = le.transform(labels)

    confusion = defaultdict(lambda: defaultdict(int))
    skf = StratifiedKFold(n_splits=4, shuffle=True, random_state=42)

    for train_idx, test_idx in skf.split(X, y):
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        # Stage 1: INDEPENDENT (0) vs RELATED (1)
        y_train_s1 = (y_train != 2).astype(int)
        model_s1 = lgb.LGBMClassifier(objective="binary", random_state=42, class_weight='balanced', verbose=-1)
        model_s1.fit(X_train, y_train_s1)

        # Stage 2: Subset to only RELATED (CONFLICT=0, DEPENDENCY=1)
        related_mask = (y_train != 2)
        X_train_s2, y_train_s2 = X_train[related_mask], y_train[related_mask]
        
        model_s2 = lgb.LGBMClassifier(objective="binary", random_state=42, class_weight='balanced', verbose=-1)
        model_s2.fit(X_train_s2, y_train_s2)

        # Predict
        pred_s1 = model_s1.predict(X_test)
        final_preds = []
        for i, is_related in enumerate(pred_s1):
            if is_related == 0:
                final_preds.append(2) # Assign INDEPENDENT
            else:
                pred_s2 = model_s2.predict(X_test[i:i+1])[0]
                final_preds.append(pred_s2) # Assign CONFLICT (0) or DEPENDENCY (1)

        for actual, pred in zip(y_test, final_preds):
            confusion[le.inverse_transform([actual])[0]][le.inverse_transform([pred])[0]] += 1

    metrics = compute_per_class_metrics(confusion)
    print("\nTWO-STAGE CASCADED CLASSIFIER RESULTS")
    print(f"{'Class':<13}{'Precision':<12}{'Recall':<12}{'F1':<10}{'Support'}")
    for label in LABELS:
        print(f"{label:<13}{metrics[label]['precision']:<12.3f}{metrics[label]['recall']:<12.3f}{metrics[label]['f1']:<10.3f}{metrics[label]['support']}")

if __name__ == "__main__":
    main()