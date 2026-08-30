# prscope
AST-driven structural analysis to catch silent cross-PR conflicts Git diff can't see. Built for DevJams'26

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
