"""FastAPI entry point — RAG Course-Note Assistant.

Endpoints:
  GET  /health     — liveness + provider status (Cloud Run smoke test)
  POST /query      — ask a question, get citation-backed answer
  GET  /params     — current retrieval + LLM params
  POST /params     — update params (TOP_K, TEMPERATURE, threshold)
"""

import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from generate.llm_client import Refusal, generate
from retrieve.retrieval import retrieve

load_dotenv()

app = FastAPI(title="RAG Course-Note Assistant — AI Textbook")

# Allow Streamlit (browser at localhost:8501) to call this API.
# Student demo: allow all origins. Phase 3 hardening: whitelist only
# http://localhost:8501 and the Cloud Run UI URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory params singleton (tune via /params without redeploy)
# ---------------------------------------------------------------------------
class Params:
    def __init__(self) -> None:
        self.top_k = int(os.getenv("TOP_K", "3"))
        self.temperature = float(os.getenv("TEMPERATURE", "0.2"))
        self.relevance_threshold = float(os.getenv("RELEVANCE_THRESHOLD", "0.35"))
        self.max_tokens = int(os.getenv("MAX_TOKENS", "512"))
        self.llm_provider = os.getenv("LLM_PROVIDER", "auto")
        self.nvidia_model = os.getenv("NVIDIA_MODEL", "z-ai/glm-5.3-flash")


params = Params()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    question: str
    provider: str | None = None      # gemini | nvidia | auto (overrides env)
    model: str | None = None         # specific NVIDIA model id (overrides NVIDIA_MODEL)


class Source(BaseModel):
    chunk_id: str
    page: int | None = None
    section: str | None = None
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]
    llm_provider: str
    llm_model: str
    latency_ms: int
    tokens_used: int


# ---------------------------------------------------------------------------
# Health (Cloud Run liveness / smoke test)
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": "0.1.0",
        "provider": params.llm_provider,
    }


# ---------------------------------------------------------------------------
# Params read/write (live tuning without redeploy)
# ---------------------------------------------------------------------------
@app.get("/params")
def get_params() -> dict:
    return {
        "top_k": params.top_k,
        "temperature": params.temperature,
        "relevance_threshold": params.relevance_threshold,
        "max_tokens": params.max_tokens,
        "llm_provider": params.llm_provider,
        "nvidia_model": params.nvidia_model,
    }


@app.post("/params")
def set_params(body: dict) -> dict:
    for key, value in body.items():
        if hasattr(params, key):
            setattr(params, key, value)
    return get_params()


# ---------------------------------------------------------------------------
# Query — the heart of the RAG pipeline
# ---------------------------------------------------------------------------
@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    start = time.time()

    # 1. Retrieve relevant chunks (empty index -> empty list, never crash)
    chunks = retrieve(req.question, top_k=params.top_k, threshold=params.relevance_threshold)

    # 2. No relevant chunks -> "Not in notes" WITHOUT calling the LLM
    if not chunks:
        return QueryResponse(
            answer="Not in notes. I could not find relevant passages in the indexed textbook corpus.",
            sources=[],
            llm_provider=params.llm_provider,
            llm_model="-",
            latency_ms=int((time.time() - start) * 1000),
            tokens_used=0,
        )

    # 3. Call the chosen LLM (Gemini / NVIDIA / auto with fallback)
    provider = req.provider or params.llm_provider
    # Only pass a model override for NVIDIA requests — passing the NVIDIA
    # model id (e.g. "z-ai/glm-5.3-flash") to GeminiAdapter would call
    # Gemini with an invalid model name and fail fast (seen as an instant
    # gemini_failed Refusal with tokens_used=0).
    model = req.model
    if model is None and provider == "nvidia":
        model = params.nvidia_model
    result = generate(
        question=req.question,
        chunks=chunks,
        provider=provider,
        model=model,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
    )

    # 4. Build response with sources (Refusal = LLM-level refusal after retrieval)
    sources = [Source(**c) for c in chunks]
    answer = "Not in notes. The indexed passages did not contain enough information to answer." if isinstance(result, Refusal) else result.answer
    return QueryResponse(
        answer=answer,
        sources=sources,
        llm_provider=result.provider,
        llm_model=result.model,
        latency_ms=int((time.time() - start) * 1000),
        tokens_used=getattr(result, "tokens_used", 0),
    )