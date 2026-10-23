# Meridin implementation scope — 20 October 2026

This update deliberately excludes **voice-note transcription** and the **complete order-creation workflow**, as requested. It does not claim that the live Meta integration is production-verified.

## Included in this code update

- Shared admin-managed catalogue vocabulary: departments, categories, subcategories, product/dress types, target gender, colours, and sizes.
- Admin UI at `/admin` → **Catalogue options** to add, edit, and archive choices.
- Authenticated client API `GET /api/catalogue-options`; client `Add product` / `Edit product` forms fetch the current active options when opened.
- Product documents and schemas now store department, category, subcategory, product type, target gender, sizes, and colours.
- Default clothing-store options are seeded at startup only when an option type has no entries. Admins can add their own options afterwards.
- Catalogue search includes the new product taxonomy fields.
- The live text-test runner can obtain a fresh JWT using `MERIDIN_API_EMAIL` and `MERIDIN_API_PASSWORD`, avoiding stale-token failures. A dedicated test workspace is strongly recommended.
- Existing intent/entity pipeline, deterministic product lookup, response validation, conversation handling, and optional CLIP visual-search implementation are retained.

## Important configuration for image-to-catalogue matching

Visual matching is optional because it needs PyTorch, Transformers, Pillow, model files, memory, and startup/download time. To enable it in the deployment:

1. Install the optional packages in `requirements-vision.txt` (install a compatible CPU PyTorch wheel first if the host does not provide one).
2. Set `VISUAL_SEARCH_ENABLED=true` in the server environment.
3. Deploy/restart the API and confirm the model can load with the available memory.
4. Sign in as a client and call `POST /api/products/visual-reindex` to index existing product images. New or edited product images are indexed on a best-effort basis.
5. Test using real, public Meta-hosted incoming image URLs and a catalogue of known images. Low-confidence matches should lead to clarification rather than an exact-match claim.

If this flag is false, text automation still runs, but image matching is unavailable. A successful code compile is not evidence that the CLIP model can load on the production host.

## Verification performed for this ZIP

- Python source compilation: passed.
- Admin JavaScript syntax check: passed.
- Client JavaScript syntax check: passed.
- Full pytest suite: **not run successfully in this environment** because the runtime did not have project dependencies such as `motor`, `pymongo/bson`, and `pwdlib`, and package installation was unavailable due to network/DNS restrictions.
- Live Instagram/Meta webhook, OAuth, MongoDB, outbound DM, and CLIP inference: not verified from this environment.

## Safe test runner

Use a dedicated test client and configure locally (do not commit credentials):

```powershell
$env:MERIDIN_API_BASE="https://your-api-host"
$env:MERIDIN_API_EMAIL="test-client@example.com"
$env:MERIDIN_API_PASSWORD="your-test-client-password"
python scripts/live_api_test.py --confirm-write
```

The runner writes synthetic test conversations to the selected tenant's database but disables sending replies to Instagram customers. It does not test image uploads or real Instagram delivery.
