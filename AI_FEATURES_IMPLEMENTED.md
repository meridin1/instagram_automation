# Meridin AI / RAG implementation notes (v3.1)

This change extends the existing application rather than replacing the Instagram integration or dashboard.

## Features added

1. **Catalogue safeguards and pagination**
   - Product facts still come from tenant-scoped MongoDB catalogue records.
   - Existing colour, size, category, brand and price filters are retained.
   - Product-search follow-ups such as `show more`, `next page`, `more designs`, `vere items` continue the prior search with a short-lived conversation-context offset.
   - If a budget search has no exact result, the system can offer above-budget alternatives only with an explicit explanation. It does not silently remove the budget constraint.
   - Stock availability is only as precise as the catalogue schema: the current product model has overall `stock` and `quantity`, plus lists of sizes/colours; it does not represent per-size/per-colour inventory quantities. Do not claim variant-level live stock until that data is stored.

2. **Tenant-specific FAQ/policy RAG**
   - New collection: `knowledge_documents`.
   - New API: `GET/POST /api/knowledge`, `PUT/DELETE /api/knowledge/{document_id}`.
   - Retrieval uses transparent token overlap and title weighting against the current tenant's active documents. This is lightweight lexical RAG and does not require a vector database or embedding model.
   - The API gets `client_id` from the authenticated session; clients cannot choose another tenant's ID.
   - Save delivery, return/exchange, payment, sizing, store and FAQ content as individual concise documents. Only use merchant-approved content.

3. **Grounded response phrasing**
   - `app/services/response_generation_service.py` optionally phrases retrieved facts in the merchant's tone/language.
   - It is called only when there are retrieved facts and both global and per-client LLM settings permit it.
   - If generation is disabled or fails, the system returns the saved source text directly. Product prices and availability continue to come from catalogue logic.

4. **Bounded conversation context**
   - Last eight messages are included as context for the intent interpreter, scoped by both client and conversation.
   - Latest intent/entities and pagination state are saved to the conversation context.
   - Context is bounded to avoid sending an unlimited transcript to the model.

5. **Quality/cost observability**
   - New collection: `ai_evaluation_events`.
   - New API: `GET /api/ai/analytics?days=30` returns event counts, intent distribution, handoff outcomes, latency, existing token usage and reviewed-quality fields.
   - New API: `POST /api/ai/evaluations/{event_id}/review` lets the authenticated client label `intent_correct`, `catalogue_correct`, `reply_grounded` and notes.
   - Accuracy values remain `null` until enough events are reviewed; confidence is not a proxy for correctness.
   - Existing token tracking is reused. Optional estimated USD cost is recorded using operator-configured `LLM_INPUT_COST_PER_MILLION_USD` and `LLM_OUTPUT_COST_PER_MILLION_USD`. Set rates from the provider pricing for the selected model; zero means unknown/not configured, not free. Rates are global and should be updated when model/provider pricing changes.

## Configure the LLM

The current default remains safe/off unless enabled. For OpenRouter, set server-side environment variables such as:

```env
LLM_ENABLED=true
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_STYLE=chat_completions
LLM_API_KEY=your_server_side_key
LLM_MODEL=meta-llama/llama-3.1-8b-instruct
```

Then enable LLM for the specific client in the existing client/automation settings. Never put the API key in frontend JavaScript or commit it. The configured provider must support OpenAI-compatible Chat Completions and JSON output for Tier 2 classification. Grounded response generation uses Chat Completions.

## Run and validate

```powershell
# From project root, using the existing Python 3.12 virtual environment
python -m pip install -r requirements.txt
python -m compileall -q app
pytest -q app/tests
uvicorn app.main:app --reload --port 8000
```

Sign in to the client dashboard, add merchant documents through the API, and test in `/docs`:
- `POST /api/knowledge` with a FAQ/policy document
- `GET /api/knowledge`
- `GET /api/ai/analytics`
- `POST /api/test/inbound` with delivery/return questions, product searches, and `show more`

The knowledge endpoints require the same authenticated client bearer token as the rest of the client API. RAG documents are not currently editable through a dedicated dashboard UI; the API is ready for that UI to be added separately.

## Limitations / honest status

- The RAG retrieval is lexical rather than embedding-based; it is a small, dependency-light first production version.
- Existing catalogue records are not migrated and no existing data is deleted.
- This code has syntax/compile checks, but a full automated test run must be completed in the project's Python 3.12 virtual environment with `requirements.txt` installed and a test MongoDB. Live Meta/LLM behavior must be tested against the real deployment separately.
