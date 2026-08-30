"""
PRScope - Streamlit Demo UI
---------------------------
Run with: streamlit run app.py
"""

import streamlit as st
import json
from pathlib import Path

from tree_sitter_poc import extract_code_and_context, extract_symbols
from engine.relation_engine import classify_pair

# 1. Page Configuration
st.set_page_config(page_title="PRScope Demo", layout="wide")
st.title("PRScope: Structural PR Analysis")
st.markdown("Detecting hidden structural relationships between independently developed Pull Requests.")

# 2. Data Loading (Cached for performance)
@st.cache_data
def load_dataset():
    with open("data/combined_python_pairs.json", "r", encoding="utf-8") as f:
        return json.load(f)["pairs"]

pairs = load_dataset()
pools_dir = Path("BulkPR-Bench-Release/data/pools")

def resolve_diff_path(raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/")
    return pools_dir / normalized.split("pools/")[-1] if "pools/" in normalized else pools_dir / normalized

# 3. UI: Pair Selection
pair_options = {
    f"{p['pr_a']} vs {p['pr_b']} ({p.get('pool', 'unknown')}) - Ground Truth: {p['label']}": p 
    for p in pairs
}
selected_pair_name = st.selectbox("Select a PR Pair from the Dataset:", list(pair_options.keys()))
pair = pair_options[selected_pair_name]

path_a = resolve_diff_path(pair["diff_a_path"])
path_b = resolve_diff_path(pair["diff_b_path"])

# 4. Engine Execution & Display
if st.button("Run Structural Analysis", type="primary"):
    if not path_a.exists() or not path_b.exists():
        st.error(f"Diff files not found at {path_a} or {path_b}. Check your pools-dir path.")
    else:
        with st.spinner("Parsing ASTs and running deterministic engine..."):
            added_a, rem_a, ctx_a = extract_code_and_context(str(path_a))
            added_b, rem_b, ctx_b = extract_code_and_context(str(path_b))
            
            sym_a, rem_sym_a = extract_symbols(added_a), extract_symbols(rem_a)
            sym_b, rem_sym_b = extract_symbols(added_b), extract_symbols(rem_b)
            
            result = classify_pair(sym_a, ctx_a, sym_b, ctx_b, rem_sym_a, rem_sym_b, str(path_a), str(path_b))

        st.divider()
        
        # 5. UI: Results Banner
        if result.label == "CONFLICT":
            st.error(f"🚨 **PREDICTION: {result.label}**")
            st.markdown(f"**Structural Evidence:** Both PRs modify or interact with the same definitions: `{sorted(result.conflict_evidence)}`")
        elif result.label == "DEPENDENCY":
            st.warning(f"⚠️ **PREDICTION: {result.label}**")
            st.markdown(f"**Structural Evidence:** One PR defines symbols the other calls: `{sorted(result.dependency_evidence)}`")
        else:
            st.success(f"✅ **PREDICTION: {result.label}**")
            st.markdown("**No structural constraints found.** These PRs are safe to merge independently.")

        st.divider()

        # 6. UI: Side-by-Side Diff Viewer
        col1, col2 = st.columns(2)
        with col1:
            st.subheader(f"PR A ({pair['pr_a']})")
            st.code(path_a.read_text(encoding="utf-8", errors="ignore"), language="diff")
        with col2:
            st.subheader(f"PR B ({pair['pr_b']})")
            st.code(path_b.read_text(encoding="utf-8", errors="ignore"), language="diff")