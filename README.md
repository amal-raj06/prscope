# PRScope: Proactive Structural Dependency Radar

## 🚀 The Git Blind Spot (The Problem)
Modern CI/CD pipelines waste immense cloud compute time and developer hours due to a fundamental flaw in version control systems: **Git only understands textual line-overlap.** 
If Developer A and Developer B modify different files but logically interact with the same underlying functions, Git assumes they are independent and merges them blindly. Teams only discover these hidden structural collisions *after* a long test suite fails or a production build breaks.

## 💡 The Solution: Proactive Structural Mapping
PRScope is an intelligent, repository-level radar that bridges the gap between basic version control and static analysis. It uses **deterministic AST (Abstract Syntax Tree) parsing** to detect cross-PR collisions *before* the CI pipeline spins up. 

If PR A modifies a function's internal logic and PR B explicitly calls that exact same function, PRScope intercepts the merge and flags the fatal collision instantly.

## 🛠️ Architecture & Tech Stack
* **Engine:** Python-based deterministic rule engine ensuring high-accuracy dependency mapping.
* **Parser:** Tree-sitter for robust Abstract Syntax Tree (AST) extraction directly from raw Git diffs across Python, Java, and C++.
* **API Bridge:** FastAPI serving as the asynchronous backend (`api.py`) to handle file validation and parsing without blocking the UI.
* **Frontend:** HTML5, Vanilla JavaScript, and Cytoscape.js rendering interactive node-based structural relationship graphs and color-coded Git diffs.

## 🔍 Engine Classification Logic (`classify_pair`)
PRScope evaluates pairs of pull requests against a strict, deterministic priority order to categorize their relationship:

* **CONFLICT (Priority 1):** One PR modifies a function that the other PR explicitly calls. This is a structural collision where merging both will likely break runtime behavior.
* **DEPENDENCY (Priority 2):** Both PRs call the same function or modify the same shared class. They share a logical dependency and touch common utilities.
* **INDEPENDENT:** No structural or semantic overlap is detected, meaning the pull requests are safe to merge.

Every classification ships with an explicit evidence list detailing the exact symbols and call sites that triggered the result, giving developers clear proof rather than a guess.