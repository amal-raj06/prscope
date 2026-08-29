"""
PRScope — eval/baselines.py
------------------------------
Two naive baselines to compare the relation engine against honestly:

1. majority_baseline: always predicts INDEPENDENT. Trivial, but proves
   why per-class F1 matters over raw accuracy — this baseline scores
   ~76% "accuracy" on the full dataset (150/198 pairs really are
   INDEPENDENT) while being completely useless for the actual task.

2. git_line_overlap_baseline: mimics what Git's REAL line-based
   merge-conflict detection does — flags CONFLICT only when two PRs
   touch OVERLAPPING LINE RANGES in the SAME file (based on each hunk's
   pre-image line numbers, i.e. the base-commit lines both PRs diverge
   from). This is literally "the existing tool" your poster tagline
   claims to go beyond: it can NEVER predict DEPENDENCY (cross-file
   relationships are structurally invisible to it), and it misses any
   CONFLICT that doesn't share literal line positions — e.g. your
   PR#41/PR#57 auth.py/api.py pitch scenario specifically, since that's
   a cross-FILE interaction with no shared lines at all.
"""

import re
from pathlib import Path
from collections import defaultdict


def extract_touched_regions(diff_path: str) -> dict:
    """
    Returns {file_path: [(start_line, end_line), ...]} based on the
    PRE-IMAGE side of each hunk (the '-' numbers in
    '@@ -start,count +start,count @@') — the base-commit line range
    both PRs are diverging from, which is exactly what a real git
    line-based merge-conflict check compares.
    """
    text = Path(diff_path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    diff_git_re = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
    hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")

    current_file = None
    regions = defaultdict(list)

    for line in lines:
        m = diff_git_re.match(line)
        if m:
            current_file = m.group(2)  # post-image path (b/...); fine even for renames
            continue
        m = hunk_re.match(line)
        if m and current_file:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) else 1
            end = start + max(count - 1, 0)
            regions[current_file].append((start, end))

    return dict(regions)


def _ranges_overlap(a_start, a_end, b_start, b_end) -> bool:
    return a_start <= b_end and b_start <= a_end


def git_line_overlap_baseline(diff_a_path: str, diff_b_path: str) -> str:
    regions_a = extract_touched_regions(diff_a_path)
    regions_b = extract_touched_regions(diff_b_path)

    shared_files = set(regions_a) & set(regions_b)
    for f in shared_files:
        for (a_start, a_end) in regions_a[f]:
            for (b_start, b_end) in regions_b[f]:
                if _ranges_overlap(a_start, a_end, b_start, b_end):
                    return "CONFLICT"

    return "INDEPENDENT"  # never predicts DEPENDENCY — by design


def majority_baseline(diff_a_path: str = None, diff_b_path: str = None) -> str:
    return "INDEPENDENT"