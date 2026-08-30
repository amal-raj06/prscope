"""
PRScope - FastAPI Backend
-------------------------
Run with: uvicorn api:app --reload
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path

# Import your deterministic engine components
from tree_sitter_poc import extract_code_and_context, extract_symbols
from engine.relation_engine import classify_pair

app = FastAPI(title="PRScope API")

# Enable CORS so your custom HTML/JS frontend can make requests to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PRAnalysisRequest(BaseModel):
    path_a: str
    path_b: str

@app.post("/analyze")
async def analyze_prs(request: PRAnalysisRequest):
    path_a = Path(request.path_a)
    path_b = Path(request.path_b)
   

    if not path_a.exists() or not path_b.exists():
        raise HTTPException(status_code=404, detail="One or both diff files could not be found.")

    # 1. AST Extraction
    added_a, rem_a, ctx_a = extract_code_and_context(str(path_a))
    added_b, rem_b, ctx_b = extract_code_and_context(str(path_b))
    
    sym_a, rem_sym_a = extract_symbols(added_a), extract_symbols(rem_a)
    sym_b, rem_sym_b = extract_symbols(added_b), extract_symbols(rem_b)
    
    # 2. Deterministic Rule Engine Execution
    result = classify_pair(sym_a, ctx_a, sym_b, ctx_b, rem_sym_a, rem_sym_b, str(path_a), str(path_b))

    # 3. JSON Serialization for Cytoscape.js
    return {
        "status": "success",
        "prediction": result.label,
        "evidence": {
            "conflict_nodes": list(result.conflict_evidence) if hasattr(result, 'conflict_evidence') else [],
            "dependency_nodes": list(result.dependency_evidence) if hasattr(result, 'dependency_evidence') else []
        },
        "diff_a": path_a.read_text(encoding="utf-8", errors="ignore"),
        "diff_b": path_b.read_text(encoding="utf-8", errors="ignore")       
    }
@app.get("/")
async def root():
    return {"message": "PRScope Engine API is running. Ready for POST requests at /analyze."}