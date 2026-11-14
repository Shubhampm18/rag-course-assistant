# GCP Deployment Report — RAG Course Assistant

**Project:** `rag-course-assistant-514120` · **Region:** `asia-south1 (Mumbai)`
**Repo:** https://github.com/Shubhampm18/rag-course-assistant (private, `main`)
**Services:** `rag-api` (FastAPI, port 8080) · `rag-ui` (Streamlit, port 8080)
**Cost target:** < $1/month — scale-to-zero Cloud Run only; no GKE/GCE/Vertex/Cloud SQL.

---

## 1. Architecture

```
Browser ──▶ rag-ui (Cloud Run, Streamlit) ──HTTPS API_URL──▶ rag-api (Cloud Run, FastAPI)
                                                              ├─ FAISS index + chunks.json
                                                              │    (downloaded from GCS at cold start)
                                                              ├─ BGE-small embeddings (CPU)
                                                              ├─ NVIDIA / Gemini keys (Secret Manager)
                                                              └─ LLM call (glm-5.3-flash default)
GitHub push ──▶ Cloud Build trigger ──▶ Docker build ──▶ Artifact Registry ──▶ Cloud Run deploy
```

Key idea: Cloud Run has **no persistent disk** — every cold start is a fresh container.
`retrieve/retrieval.py::load_index()` therefore downloads `faiss.idx` + `chunks.json`
from bucket `rag-index-514120` into `/tmp` when local files are missing.

---

## 2. One-time setup (Console UI)

### 2.1 Project & APIs
1. Create/select project `rag-course-assistant`.
2. Enable APIs (APIs & Services → Library, or direct links):
   - `run.googleapis.com` (Cloud Run)
   - `artifactregistry.googleapis.com`
   - `storage.googleapis.com`
   - `secretmanager.googleapis.com`
   - `cloudbuild.googleapis.com`

### 2.2 GCS bucket (index files)
1. Cloud Storage → **Create bucket**
2. Name: `rag-index-514120` · Location type: **Region** `asia-south1 (Mumbai)` ·
   Storage class: **Standard** · Access control: **Uniform** · keep **public access prevention ON**.
3. Objects tab → **Upload files** → `faiss.idx` (1.1 MB) + `chunks.json` (1.3 MB) at **bucket root** (no folder prefix).

### 2.3 Secrets (Secret Manager → Create secret)
| Name | Value | Everything else |
|---|---|---|
| `NVIDIA_API_KEY` | raw `nvapi-...` key (no quotes/spaces) | defaults |
| `GOOGLE_API_KEY` | raw Gemini key | defaults |

⚠️ Type the env/secret names carefully — a trailing space breaks the deployment
(see §6 Troubleshooting).

---

## 3. Deploy rag-api ("Deploy from Git repository")

Cloud Run → **Deploy a web service** → **Continuously deploy from a Git repository** → GitHub.

1. Authorize the Google Cloud Build GitHub app on `Shubhampm18/rag-course-assistant`.
2. Branch: `main` · Build type: **Dockerfile** · Dockerfile location: **`/Dockerfile`**
3. Service configuration:
   - Service name: `rag-api` · Region: `asia-south1 (Mumbai)`
   - Authentication: **Allow public access** · Billing: **Request-based**
   - Auto-scaling: **min 0 / max 5** · Ingress: **All**
4. Containers, Networking, Security:
   - Container port: `8080` · Memory `2 GiB` · CPU `1` · Request timeout `300 s`
   - Max concurrent requests: `10`
   - Environment variables:
     | Name | Value |
     |---|---|
     | `FAISS_INDEX_PATH` | `/tmp/faiss.idx` |
     | `CHUNKS_META_PATH` | `/tmp/chunks.json` |
     | `GCS_INDEX_BUCKET` | `rag-index-514120` |
     | `LLM_PROVIDER` | `nvidia` |
     | `NVIDIA_MODEL` | `z-ai/glm-5.3-flash` |
   - Secrets exposed as environment variables:
     | Secret | Version | Env var name |
     |---|---|---|
     | `NVIDIA_API_KEY` | latest | `NVIDIA_API_KEY` |
     | `GOOGLE_API_KEY` | latest | `GOOGLE_API_KEY` |
5. Create → first build runs (~5–10 min).

### IAM grant (required once)
If deploy fails with *"Permission denied on secret … roles/secretmanager.secretAccessor"*:
**IAM & Admin → IAM → `934403447461-compute@developer.gserviceaccount.com` → Edit
(pencil) → Add another role → Secret Manager Secret Accessor → Save**, then
**Cloud Run → rag-api → Edit & deploy new revision → Deploy**.

---

## 4. Deploy rag-ui (same Git flow, second Dockerfile)

Repo contains **`Dockerfile.ui`** (Streamlit entry point on port 8080).

Cloud Run → Deploy a web service → Git → repo `rag-course-assistant` → branch `main`:

- Build type: **Dockerfile** · Dockerfile location: **`/Dockerfile.ui`** ← must NOT be `/Dockerfile`
- Service name: `rag-ui` · Region `asia-south1 (Mumbai)` · Allow public access ·
  Request-based · min 0 / max 5 · Ingress All
- Containers tab: port `8080` · Memory `1 GiB` · CPU `1` · **Request timeout `3600 s`**
- Networking tab: **Session affinity: On** (Streamlit WebSockets)
- Variables & Secrets → Environment variables:
  | Name | Value |
  |---|---|
  | `API_URL` | `https://rag-api-934403447461.asia-south1.run.app` |
- **No secrets on the UI.**

---

## 5. Verification

1. **Health** — browser: `https://rag-api-934403447461.asia-south1.run.app/health`
   ```json
   {"status":"ok","version":"0.1.0","provider":"nvidia"}
   ```
   (First hit after idle = cold start, up to ~90 s: model download + index download.)
2. **Query** — browser: `https://…/docs` → POST /query → Try it out:
   ```json
   { "question": "How do LLMs represent text as tokens?" }
   ```
   Correct response: HTTP 200 with a grounded `answer`, inline citations
   (`[p.27, AI Engineering:p27_c031]`), relevant `sources` (page/section/score),
   `tokens_used > 0`, `llm_model: z-ai/glm-5.3-flash`.
3. **Off-topic refusal** — e.g. *"Who won the cricket world cup?"* →
   "Not in notes" refusal (calibrated threshold + refusal prompt; never hallucinates).
4. **UI** — open the rag-ui URL → chat answers with citations; Dashboard + About load;
   sidebar shows *Backend: online (ok, provider=nvidia)* and **721 chunks**.

---

## 6. Troubleshooting — the three failures we hit (and fixes)

| # | Symptom (exact error) | Root cause | Fix |
|---|---|---|---|
| 1 | `Permission denied on secret: projects/…/NVIDIA_API_KEY/versions/latest … must be granted 'Secret Manager Secret Accessor'` | Runtime service account lacked IAM role on the secrets | Grant `roles/secretmanager.secretAccessor` to `…-compute@developer…` (project or per-secret), redeploy revision |
| 2 | Build log: `the --mount option requires BuildKit` → `ERROR: build step 0 … failed` | Dockerfile used a BuildKit cache mount; Cloud Build legacy builder has no BuildKit | Remove `--mount=type=cache,...` → plain `RUN uv sync --frozen --no-dev --no-install-project` |
| 3 | `/query` returns "Not in notes" with `tokens_used: 0` in ~80 ms (no LLM call) | Env var name had a **trailing space** (`'NVIDIA_API_KEY '`) → `os.getenv("NVIDIA_API_KEY")` was None → OpenAI client failed instantly | Delete the broken env var; re-add with exact name `NVIDIA_API_KEY`; redeploy revision |

Debugging rule: read the **build log tail** (Cloud Build → History → failed build) and
**Cloud Run → Observability → Logs** before changing anything.

---

## 7. Cost guardrails

| Control | Value | Where verified |
|---|---|---|
| Min instances (both services) | `0` (scale-to-zero) | Cloud Run → YAML → `autoscaling.knative.dev/minScale: 0` |
| Max instances (both services) | `5` (abuse fuse) | Cloud Run → YAML → `run.googleapis.com/maxScale: 5` |
| Billing mode | Request-based (CPU only during requests) | Revision detail |
| Budget alert | **$10**, thresholds 50/90/100 %, email | Billing → Budgets & alerts |
| Resources | api: 2 GiB/1 vCPU · ui: 1 GiB/1 vCPU | Revision detail |

Expected steady-state spend: **$0/month** (Cloud Run free tier covers demo usage;
bucket holds 2.4 MB; 2 secrets within free tier).

---

## 8. Teardown checklist (after the demo/viva — stops all billing)

Delete in this order:

1. Cloud Run → **rag-ui** → Delete
2. Cloud Run → **rag-api** → Delete
3. Cloud Build → **Triggers** → delete `rmgpgab-rag-api-…` and `rmgpgab-rag-ui-…`
4. Secret Manager → delete `NVIDIA_API_KEY`, `GOOGLE_API_KEY`
5. Cloud Storage → delete bucket `rag-index-514120` (force-delete contents)
6. Artifact Registry → delete `cloud-run-source-deploy` and `rag-images`
7. Billing → Budgets → delete the $10 budget
8. (Optional) APIs & Services → disable the 5 APIs — not billable, just tidy

---

## 9. Viva demo script (5 minutes)

1. **Show the UI** (rag-ui URL): ask a question, get a cited answer; show Dashboard.
2. **Show the API contract** (`/docs`): GET /health, GET/POST /params, POST /query.
3. **Show architecture evidence**: Cloud Run service list (2 services, asia-south1),
   rag-api YAML (min 0 / max 5, secrets via `secretKeyRef`, index env vars),
   GCS bucket (2.4 MB index), Secret Manager (2 secrets + secretAccessor IAM).
4. **Show CI/CD**: Cloud Build history — push to `main` auto-builds & deploys
   (commit SHAs visible); mention the two failures and fixes from §6 as debugging evidence.
5. **Show cost discipline**: YAML min-instances 0, request-based billing, $10 budget alert.

---

## 10. Deployed URLs (live)

- rag-api: https://rag-api-934403447461.asia-south1.run.app  (`/health`, `/docs`, `/query`, `/params`)
- rag-ui:  https://rag-ui-934403447461.asia-south1.run.app
