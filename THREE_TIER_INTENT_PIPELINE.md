# Meridin three-tier intent and entity pipeline

## Runtime behaviour

1. **Tier 1** always runs first: deterministic rules, the shared local TF-IDF/Logistic Regression classifier, regex feature extraction, and the BIO entity extractor.
2. **Tier 2 — full interpretation** runs only when Tier 1 cannot confidently resolve the intent and that client has LLM enabled. One structured call returns the primary intent, secondary intents, and extractable features.
3. **Tier 2 — feature enrichment** can also run when Tier 1 has already resolved the intent but an explicit feature phrase appears only partly captured (for example, `sky blue` captured as only `blue`, or a specific print/style missed by the local dictionary). The Tier 1 primary intent is retained. Only allowed, grounded feature values are merged; reliable Tier 1 values are not overwritten, except a partial colour/pattern value can be refined by a longer phrase grounded in the message.
4. **Tier 3** handles unresolved/low-confidence/invalid interpretation using the existing clarification and human-handover policies. Missing fields that the customer never mentioned do not trigger an LLM call.

The model interprets messages; it does not determine stock, prices, product policies, delivery promises, or working hours. Tenant-scoped catalogue and business settings remain the source of truth.

## Shared intent taxonomy

`greeting`, `thanks`, `goodbye`, `product_search`, `product_availability`, `product_inquiry`, `product_price`, `product_details`, `product_alternatives`, `product_size`, `product_color`, `product_link`, `location_query`, `delivery_query`, `delivery_time_query`, `business_hours_query`, `order_status`, `order_request`, `cancel_order`, `return_request`, `exchange_request`, `complaint`, `human_handoff`, `discount_inquiry`, `payment_query`, `delivery_issue`, `return_policy_query`, `exchange_policy_query`, `product_comparison`, `media_product_identification`, `unknown`.

## Configure Tier 2

Set server-side environment variables in Render or `.env`: `LLM_ENABLED=true`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_API_STYLE`, `LLM_MODEL`, `TIER1_CONFIDENCE_THRESHOLD` (default 0.65), and `TIER2_CONFIDENCE_THRESHOLD` (default 0.72). Each client must also enable LLM use and remain within its configured usage limits. No model weights are bundled. Keep LLM disabled for local-only operation.

## Tests

Run `python -m compileall -q app` and `pytest -q app/tests`. Unit tests mock the LLM and do not make live provider calls. Live Render/Instagram validation still requires the deployed environment and connected Meta account.
