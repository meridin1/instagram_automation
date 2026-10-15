# Phase 4 — Semantic Product Search

Phase 4 adds local semantic product search using sentence-transformers embeddings.
MongoDB remains the catalog source of truth.

## What changed

- Product catalog fields are converted into searchable text.
- `sentence-transformers/all-MiniLM-L6-v2` creates product/query embeddings.
- Product embeddings are stored inside each MongoDB product document.
- Search is tenant-isolated with `client_id`.
- COLOR, SIZE, PRICE and CATEGORY entities are hard filters before semantic ranking.
- Semantic similarity ranks the remaining real catalog products.
- No LLM and no RAG are used.
- Existing deterministic price/availability/color/link behavior remains intact when a conversation already has a product context.

## Install

Use the same Python 3.12 virtual environment as the project:

```powershell
python -m pip install -r requirements.txt
```

The first semantic search may download `all-MiniLM-L6-v2` from Hugging Face. The model is cached locally after that.

## Reindex a client's active catalog

```powershell
python -c "import asyncio; from app.services.semantic_search_service import reindex_products; print(asyncio.run(reindex_products('YOUR_CLIENT_ID')))"
```

Or use Swagger:

`POST /api/search/products/reindex`

```json
{
  "client_id": "YOUR_CLIENT_ID"
}
```

## Test semantic search in Swagger

`POST /api/search/products`

```json
{
  "client_id": "YOUR_CLIENT_ID",
  "query": "Show me a black kurti in XL under 1500",
  "entities": {
    "by_type": {
      "COLOR": ["black"],
      "CATEGORY": ["kurti"],
      "SIZE": ["XL"],
      "PRICE": [1500.0]
    }
  },
  "limit": 5
}
```

## Existing inbound API

`POST /api/test/inbound` now passes the original customer text into the response layer. If there is no current product context, Phase 4 can search the client's catalog for product price, availability, colour, link, and alternative requests.

## Tests

```powershell
python -m unittest discover -s app/tests -v
```

The Phase 4 unit tests do not download a model; they validate catalog text construction and hard-constraint safety. The actual embedding backend is exercised when `/api/search/products` or a search-backed inbound message is called after installing the Phase 4 requirements.
