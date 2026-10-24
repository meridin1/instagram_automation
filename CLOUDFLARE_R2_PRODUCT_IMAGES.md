# Cloudflare R2 product image uploads for Meridin

Meridin's Add product/Edit product form now accepts an image file instead of asking the merchant to paste an image URL. The FastAPI backend uploads the image to Cloudflare R2 and saves the returned public URL in the product's existing `image_url` field. Existing product records with URLs continue to work.

## 1. Create an R2 bucket

1. Sign in to the Cloudflare dashboard and select your account.
2. Open **R2 Object Storage** and create a bucket, for example `meridin-product-images`.
3. Keep the bucket name for `R2_BUCKET_NAME`.
4. Open R2 API tokens / Manage R2 API Tokens and create a token with **Object Read & Write** permission scoped to this bucket. Copy the Access Key ID and Secret Access Key when shown; the secret is only shown once.
5. Find your Cloudflare **Account ID** from the account overview or R2 dashboard.

The S3-compatible endpoint used by the app is `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.

## 2. Set up a public image URL

The saved `image_url` must be publicly reachable by browsers and Meta/Instagram's media fetcher.

Recommended: connect a custom domain such as `images.yourdomain.com` to the R2 bucket from the bucket's **Settings → Custom Domains** section. Follow Cloudflare's DNS/domain activation steps. Then set `R2_PUBLIC_BASE_URL=https://images.yourdomain.com`.

For a temporary test, you can enable the bucket's `r2.dev` public development URL in bucket settings and use that exact base URL. Cloudflare rate-limits `r2.dev`; use a custom domain for production. Do not put the S3 API endpoint in `R2_PUBLIC_BASE_URL`—that is the upload endpoint, not a public object-serving URL.

Only make the product-image bucket public. Do not store private documents, access tokens, customer data, or other secrets in it. Anyone with a public image URL can view that image.

## 3. Configure local `.env`

Copy the relevant variables from `.env.example` into your local `.env` and fill them with your own values:

```env
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_ACCESS_KEY_ID=your_r2_access_key_id
R2_SECRET_ACCESS_KEY=your_r2_secret_access_key
R2_BUCKET_NAME=meridin-product-images
R2_PUBLIC_BASE_URL=https://images.yourdomain.com
PRODUCT_IMAGE_MAX_BYTES=8388608
```

Keep the access key and secret server-side. Never use them in frontend JavaScript, a Vite `VITE_` variable, Git, or a public screenshot. Add `.env` to `.gitignore` and rotate any key accidentally exposed.

Install the added S3 client dependency and run locally:

```powershell
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Sign in to the dashboard, open Catalogue → Add product, select a JPEG/PNG/WebP image (maximum 8 MB), and save the product. The UI uploads first and then saves the resulting URL with the product. Edit product allows selecting a replacement image; leaving the file picker empty keeps the current image.

## 4. Configure Render

In Render → your Meridin web service → **Environment**, add the same five `R2_*` values and `PRODUCT_IMAGE_MAX_BYTES`. Do not change `TOKEN_ENCRYPTION_KEY` or any Meta/JWT secret for this feature. Deploy the updated code after adding the variables. Environment variable changes may trigger a redeploy; confirm the latest deployment is live.

## 5. Smoke test / troubleshooting

- `POST /api/products/upload-image` requires the same authenticated client JWT as the product API and accepts multipart form field `file`.
- Supported file types are JPEG, PNG and WebP; max size is 8 MiB.
- `503`: one or more R2 environment values are missing.
- `502`: verify Account ID, bucket name, Access Key ID/Secret, and that the token has Object Read & Write permission for that bucket.
- Upload succeeds but image does not display: check `R2_PUBLIC_BASE_URL`, custom-domain status, public read access, HTTPS, and that the URL opens in a private browser window.
- Do not paste the R2 secret into support chats or logs.

The endpoint uploads images to a tenant-specific prefix (`products/<client_id>/...`) and uses random filenames to avoid collisions. Product documents remain isolated by the existing `client_id` database filter. The R2 bucket itself is shared; object-prefix separation is organizational, not a substitute for keeping the R2 credentials server-side.
