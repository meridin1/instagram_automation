# Optional CLIP image-to-catalogue search

Meridin can compare a customer-sent Instagram image against product images in that client's catalogue. It uses CLIP image embeddings and cosine similarity; it does not ask an LLM to describe the image.

## Enable locally (CPU)

1. Activate the project's Python environment.
2. Install CPU PyTorch using the official CPU wheel index:

   ```bash
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   pip install -r requirements-vision.txt
   ```

3. Add these values to `.env`:

   ```dotenv
   VISUAL_SEARCH_ENABLED=true
   CLIP_MODEL_NAME=openai/clip-vit-base-patch32
   VISUAL_SIMILARITY_THRESHOLD=0.72
   VISUAL_MATCH_MARGIN=0.035
   VISUAL_IMAGE_MAX_BYTES=8388608
   ```

4. Restart the app. The first inference downloads the configured CLIP model from Hugging Face, so the deployment needs outbound network access and enough disk/RAM. The model is loaded lazily and reused by the process.
5. Add valid HTTPS product image URLs to each product. Newly created/updated products are indexed when visual search is enabled. Reindex existing products with an authenticated request:

   `POST /api/products/visual-reindex`

   The endpoint only processes the authenticated client's products.

## Runtime behavior

- Incoming text intent/entity extraction and image embedding run concurrently.
- The vector is compared only with indexed products belonging to the same client.
- Visual candidates are ranked by cosine similarity. Text attributes such as colour, size, and budget filter the visual candidates after image similarity retrieval.
- If the best match is ambiguous, the bot lists candidates or asks a clarification instead of guessing a price.
- If the photo cannot be downloaded, the image is invalid, the model isn't installed, or no candidate passes the threshold, the normal safe fallback remains available.
- Incoming image URLs must be HTTPS URLs on Meta/Instagram CDN domains. Product image URLs must be public HTTPS URLs. Private/local addresses and non-image responses are rejected; downloads are size-limited and redirects are revalidated.
- The threshold is a starting value, not a calibrated production guarantee. Evaluate it on real product/customer image pairs and tune it before enabling for clients.

## Important deployment note

CLIP/PyTorch significantly increases deployment size and memory use. Keep visual search disabled on deployments that don't have the optional dependencies/resources. Do not enable it until product image indexing, the Meta CDN URL format, similarity thresholds, and webhook response latency have been tested on the target host.
