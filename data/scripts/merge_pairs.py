"""
PRScope — merge per-pool extracted pair files into one combined dataset.

Usage:
    python merge_pairs.py --files data/click_pairs.json data/attrs_pairs.json ... --out data/combined_pairs.json
"""

import json
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", required=True, help="List of per-pool pair JSON files to merge")
    parser.add_argument("--out", required=True, help="Output combined JSON file path")
    args = parser.parse_args()

    all_pairs = []
    per_file_stats = []

    for fpath in args.files:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        pool_name = fpath.split("\\")[-1].split("/")[-1].replace("_pairs.json", "")
        for pair in data["pairs"]:
            pair["pool"] = pool_name
            all_pairs.append(pair)
        per_file_stats.append({"pool": pool_name, **data["stats"]})

    combined_stats = {
        "total_pairs": len(all_pairs),
        "conflict": sum(1 for p in all_pairs if p["label"] == "CONFLICT"),
        "dependency": sum(1 for p in all_pairs if p["label"] == "DEPENDENCY"),
        "independent": sum(1 for p in all_pairs if p["label"] == "INDEPENDENT"),
        "pools_included": [s["pool"] for s in per_file_stats],
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"stats": combined_stats, "per_pool_stats": per_file_stats, "pairs": all_pairs}, f, indent=2)

    print("Merge complete.")
    print(json.dumps(combined_stats, indent=2))
    print(f"\nWrote {len(all_pairs)} combined pairs to {args.out}")


if __name__ == "__main__":
    main()