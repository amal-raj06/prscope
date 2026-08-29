"""
PRScope — BulkPR-Bench extraction script
------------------------------------------
Reads a pool.json + diffs/ folder from BulkPR-Bench-Release and produces
a clean, labeled set of PR pairs for PRScope's DEPENDENCY / CONFLICT /
INDEPENDENT classification task.

Usage:
    python extract_pairs.py --pool data/pools/click --out click_pairs.json

Expects the BulkPR-Bench-Release repo to be cloned somewhere, and this
script to be pointed at one pool's folder (the one containing pool.json
and a diffs/ subfolder).
"""

import json
import argparse
import random
from pathlib import Path
from itertools import combinations


def load_pool(pool_dir: Path):
    pool_json_path = pool_dir / "pool.json"
    if not pool_json_path.exists():
        raise FileNotFoundError(f"Could not find pool.json at {pool_json_path}")
    with open(pool_json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def diff_path_for(pool_dir: Path, pr_id: str):
    """
    BulkPR-Bench diff files are named like PR-01.diff, PR-02.diff, etc.
    Adjust the pattern here if a given pool uses a different naming scheme.
    """
    candidate = pool_dir / "diffs" / f"{pr_id}.diff"
    return candidate if candidate.exists() else None


def all_pr_ids_from_diffs(pool_dir: Path):
    diffs_dir = pool_dir / "diffs"
    ids = []
    for p in diffs_dir.glob("*.diff"):
        ids.append(p.stem)  # "PR-01.diff" -> "PR-01"
    return sorted(ids)


def extract_pairs(pool_dir: Path, max_independent_per_pool: int = 30, seed: int = 42):
    pool = load_pool(pool_dir)
    constraints = pool.get("constraints", [])

    labeled_pairs = []
    related_pair_keys = set()  # to exclude from INDEPENDENT sampling later

    skipped_higher_order = 0
    skipped_other_types = 0

    for c in constraints:
        ctype = c.get("type")

        if ctype == "forbidden_set":
            members = c.get("members", [])
            if len(members) != 2:
                skipped_higher_order += 1
                continue
            pr_a, pr_b = members
            diff_a = diff_path_for(pool_dir, pr_a)
            diff_b = diff_path_for(pool_dir, pr_b)
            if diff_a is None or diff_b is None:
                continue  # skip if a diff file is missing
            labeled_pairs.append({
                "pr_a": pr_a,
                "pr_b": pr_b,
                "diff_a_path": str(diff_a),
                "diff_b_path": str(diff_b),
                "label": "CONFLICT",
                "direction": None,
                "source_relation_type": ctype,
                "visibility": c.get("visibility"),
            })
            related_pair_keys.add(frozenset([pr_a, pr_b]))

        elif ctype == "depends_on":
            pr_source = c.get("source")
            pr_target = c.get("target")
            diff_source = diff_path_for(pool_dir, pr_source)
            diff_target = diff_path_for(pool_dir, pr_target)
            if diff_source is None or diff_target is None:
                continue
            labeled_pairs.append({
                "pr_a": pr_source,
                "pr_b": pr_target,
                "diff_a_path": str(diff_source),
                "diff_b_path": str(diff_target),
                "label": "DEPENDENCY",
                "direction": f"{pr_source} depends_on {pr_target}",
                "source_relation_type": ctype,
                "visibility": c.get("visibility"),
            })
            related_pair_keys.add(frozenset([pr_source, pr_target]))

        else:
            # duplicate, supersedes, must_reject, or anything else —
            # excluded from the MVP 3-way classification task on purpose.
            skipped_other_types += 1
            continue

    # --- Build INDEPENDENT examples: PR pairs in this pool with NO relation ---
    all_ids = all_pr_ids_from_diffs(pool_dir)
    random.seed(seed)
    all_possible_pairs = list(combinations(all_ids, 2))
    random.shuffle(all_possible_pairs)

    independent_count = 0
    for pr_a, pr_b in all_possible_pairs:
        if independent_count >= max_independent_per_pool:
            break
        if frozenset([pr_a, pr_b]) in related_pair_keys:
            continue
        diff_a = diff_path_for(pool_dir, pr_a)
        diff_b = diff_path_for(pool_dir, pr_b)
        if diff_a is None or diff_b is None:
            continue
        labeled_pairs.append({
            "pr_a": pr_a,
            "pr_b": pr_b,
            "diff_a_path": str(diff_a),
            "diff_b_path": str(diff_b),
            "label": "INDEPENDENT",
            "direction": None,
            "source_relation_type": "no_constraint_found",
            "visibility": None,
        })
        independent_count += 1

    stats = {
        "total_pairs": len(labeled_pairs),
        "conflict": sum(1 for p in labeled_pairs if p["label"] == "CONFLICT"),
        "dependency": sum(1 for p in labeled_pairs if p["label"] == "DEPENDENCY"),
        "independent": sum(1 for p in labeled_pairs if p["label"] == "INDEPENDENT"),
        "skipped_higher_order_conflicts": skipped_higher_order,
        "skipped_other_relation_types": skipped_other_types,
        "total_prs_in_pool": len(all_ids),
    }

    return labeled_pairs, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", required=True, help="Path to a pool folder, e.g. data/pools/click")
    parser.add_argument("--out", required=True, help="Output JSON file path")
    parser.add_argument("--max-independent", type=int, default=30,
                         help="Max number of INDEPENDENT pairs to sample per pool")
    args = parser.parse_args()

    pool_dir = Path(args.pool)
    pairs, stats = extract_pairs(pool_dir, max_independent_per_pool=args.max_independent)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "pairs": pairs}, f, indent=2)

    print("Extraction complete.")
    print(json.dumps(stats, indent=2))
    print(f"\nWrote {len(pairs)} labeled pairs to {args.out}")


if __name__ == "__main__":
    main()