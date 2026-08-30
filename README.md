# PRScope: Proactive Structural Dependency Radar

## 🚀 The Git Blind Spot (The Problem)
Modern CI/CD pipelines waste immense cloud compute time and developer hours due to a fundamental flaw in version control systems: **Git only understands textual line-overlap.**
If Developer A and Developer B modify different files but logically interact with the same underlying functions, Git assumes they are independent and merges them blindly. Teams only discover these hidden structural collisions *after* a long test suite fails or a production build breaks.

## 💡 The Solution: Proactive Structural Mapping
PRScope is an intelligent, repository-level radar that bridges the gap between basic version control and static analysis. It uses **deterministic AST (Abstract Syntax Tree) parsing** to detect cross-PR collisions *before* the CI pipeline spins up. 

If PR A modifies a function's internal logic and PR B explicitly calls that exact same function, PRScope intercepts the merge and flags the fatal collision instantly.

## 🛠️ Architecture
* **Engine:** Python-based deterministic rule engine ensuring high-accuracy dependency mapping.
* **Parser:** Tree-sitter for robust Abstract Syntax Tree (AST) extraction directly from raw Git diffs.
* **API Bridge:** FastAPI serving as the asynchronous backend to handle complex parsing without blocking the UI.
* **Frontend:** Cytoscape.js rendering the interactive node-based structural relationship graphs.

### Asynchronous Data Flow
```mermaid
sequenceDiagram
    autonumber
    actor Developer
    participant UI as Cytoscape Dashboard (Frontend)
    participant API as FastAPI (Backend Bridge)
    participant Parser as Tree-sitter (Multi-Lang AST)
    participant Engine as Deterministic Relation Engine

    Developer->>UI: Selects PR-A & PR-B (Click Analyze)
    UI->>API: POST /analyze {path_a, path_b}
    
    API->>Parser: extract_code_and_context(path_a)
    Parser-->>API: AST Symbols (Python/Java/C++)
    
    API->>Parser: extract_code_and_context(path_b)
    Parser-->>API: AST Symbols (Python/Java/C++)
    
    API->>Engine: classify_pair(symbols_a, symbols_b)
    
    alt Structural Collision Detected
        Engine-->>API: CONFLICT (Priority 1) + Evidence Nodes
    else Shared Utilities Detected
        Engine-->>API: DEPENDENCY (Priority 2) + Evidence Nodes
    else No Overlap
        Engine-->>API: INDEPENDENT
    end
    
    API-->>UI: JSON {prediction, diff_texts, evidence_list}
    UI->>UI: formatDiff() - Apply Git Red/Green Colors
    UI->>UI: highlight_evidence() - Tag Collision Nodes
    UI->>UI: cy.layout() - Render Directed Graph

flowchart TD
    Start([Start: classify_pair]) --> Extract[Extract AST Symbols for PR A & PR B]
    
    Extract --> EvalConflict{Structural Collision?}
    
    EvalConflict -- "PR A modifies function called by PR B\nOR\nPR B modifies function called by PR A" --> ConflictState[Priority 1: Escalate to CONFLICT]
    
    EvalConflict -- "No Cross-Modification" --> EvalDependency{Shared Logic?}
    
    EvalDependency -- "Both PRs call the same function\nOR\nBoth PRs modify the same class" --> DependencyState[Priority 2: Flag as DEPENDENCY]
    
    EvalDependency -- "No overlap detected" --> IndependentState[Flag as INDEPENDENT]
    
    ConflictState --> FormResult[Construct JSON Payload with Evidence Nodes]
    DependencyState --> FormResult
    IndependentState --> FormResult
    
    FormResult --> End([End: Return Result to API])

    style ConflictState fill:#ffebe9,stroke:#cf222e,stroke-width:2px,color:#cf222e
    style DependencyState fill:#fff8c5,stroke:#9a6700,stroke-width:2px,color:#9a6700
    style IndependentState fill:#e6ffed,stroke:#1a7f37,stroke-width:2px,color:#1a7f37