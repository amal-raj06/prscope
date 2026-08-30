# PRScope
### Proactive Structural Dependency Radar

**Stop merging code that breaks in production. Start catching structural collisions before CI even spins up.**

---

## 🚀 The Problem: Git's Blind Spot

Modern CI/CD pipelines burn enormous amounts of compute time and developer hours chasing a failure mode that shouldn't exist anymore: **Git only understands textual line-overlap.**

If Developer A and Developer B touch *different files* but their changes logically collide — one modifies a function's contract, the other calls it and depends on the old behavior — Git sees no conflict at all. It merges blindly. The team only finds out something is wrong after a long test suite fails, a staging deploy breaks, or worse, it ships.

This is a structural problem hiding inside a textual tool. Line-diffing was never designed to reason about function calls, class hierarchies, or shared state — and as codebases and PR velocity grow, that gap gets more expensive every sprint.

## 💡 The Solution: Proactive Structural Mapping

PRScope closes that gap. It's a repository-level radar that sits between your version control system and your CI pipeline, using **deterministic AST (Abstract Syntax Tree) parsing** to understand what your code actually *does* — not just which lines changed.

Instead of waiting for a test suite to fail, PRScope statically analyzes every open pull request, builds a symbol-level dependency graph, and flags the exact moment two PRs touch the same logical surface — before either one merges.

If PR A changes a function's internal logic and PR B explicitly calls that same function, PRScope catches the collision instantly, tells you exactly which symbols are involved, and shows you the evidence — no guesswork, no false confidence from a green checkmark that never should have been green.

## ✨ Why It Matters

- **Catch collisions pre-merge, not post-mortem.** Move conflict detection from "after the build breaks" to "before the PR is even approved."
- **Deterministic, not probabilistic.** No LLM guesswork or fuzzy heuristics — PRScope's rule engine gives the same answer every time, with evidence you can audit.
- **Multi-language AST parsing.** Built on Tree-sitter, so PRScope reasons about real code structure across Python, Java, C++, and more — not just diff text.
- **Built for scale.** An asynchronous FastAPI backend means parsing and classification never block the UI, even across large, busy repositories.
- **See the collision, don't just get told about it.** An interactive Cytoscape.js graph renders the actual relationship between conflicting PRs, so reviewers understand *why* something was flagged, not just *that* it was.

## 🛠️ Architecture

| Layer | Technology | Role |
|---|---|---|
| **Engine** | Python | Deterministic rule engine for high-accuracy dependency classification |
| **Parser** | Tree-sitter | Multi-language AST extraction directly from raw Git diffs |
| **API Bridge** | FastAPI | Asynchronous backend handling parsing without blocking the UI |
| **Frontend** | Cytoscape.js | Interactive node-based rendering of structural relationship graphs |

## 🔍 How Classification Works

Every PR pair is evaluated against a strict priority order:

1. **CONFLICT (Priority 1)** — One PR modifies a function that the other PR calls. This is a structural collision: merging both is likely to break behavior.
2. **DEPENDENCY (Priority 2)** — Both PRs call the same function, or both modify the same class, without a direct modify/call collision. Not necessarily breaking, but worth a second look.
3. **INDEPENDENT** — No structural overlap detected. Safe to merge without further review.

Each result ships with an evidence list — the specific symbols, functions, and call sites that drove the classification — so nothing is a black-box verdict.

## 📌 Status

PRScope is under active development. Contributions, issues, and feature requests are welcome.

---

*Built for teams tired of finding out about conflicts the hard way.*