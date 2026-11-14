# Model Card — RAG Course-Note Assistant (AI Textbook)

## Intended use
Private study assistant for the users own AI textbook PDFs only. NOT for professional legal, medical, or financial advice.

## Models
- Primary LLM: Gemini 2.5 Flash via google-genai free-tier API (default)
- Alternative LLM: NVIDIA NIM hosted on build.nvidia.com (meta/llama-3.1-8b-instruct), OpenAI-compatible
- Embeddings: BAAI/bge-small-en-v1.5 (33M params, 384-dim, CPU)

## Data
Retrieval corpus = user-uploaded AI textbook PDFs (GCS, private bucket). No fine-tuning data.
Data license: private single-user study use. Embeddings treated as private (derived from copyrighted text).

## Performance (fill after eval)
- Hit@3: TBD
- Citation accuracy: TBD
- Refusal accuracy (out-of-scope): TBD
- p95 latency: TBD
- Cost/query: ~$0.0001 (Cloud Run only)

## Limitations
- Not a substitute for professional advice
- Scanned/OCR PDFs may have extraction errors; low-confidence pages flagged
- Tables may need manual review; heading-aware chunking mitigates fragmentation

## Sustainability
Small embeddings (33M) + small LLM (Flash) + serverless scale-to-zero.
Est. CO2/query: ~0.0001 kg (Cloud Run vCPU-s based estimate).
An always-on Vertex endpoint would be ~800x more energy and cost.

## Bias audit
Test questions should cover diverse topics from the textbook (e.g. fairness, bias in embeddings).