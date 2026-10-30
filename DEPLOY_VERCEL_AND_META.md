# Meridin Instagram Automation — Vercel deployment and custom domains

This repository is deployed as **one Vercel project** with three custom domains:

- `https://ig-api.meridin.in` — canonical API and Meta webhook origin
- `https://ig-app.meridin.in` — client dashboard
- `https://ig-admin.meridin.in` — admin dashboard

All three hostnames must be attached to the **same Vercel project and production deployment** for this single-project architecture.

## How routing works

The FastAPI application is deployed as one Vercel Python function. It serves the existing client and admin static directories as well as API routes.

- Visiting `https://ig-app.meridin.in/` redirects to `/dashboard/`.
- Visiting `https://ig-admin.meridin.in/` redirects to `/admin/`.
- Visiting `https://ig-api.meridin.in/` returns a small service-status JSON response.
- Existing frontend JavaScript uses relative `/api/...` requests. Those requests intentionally go to the dashboard's own hostname, which is attached to the same Vercel project and reaches the same FastAPI application.
- Meta webhook URLs use the canonical API hostname from `PUBLIC_BASE_URL`.

Do not create three separate Vercel projects for these domains unless the application architecture is intentionally split later.

## Vercel project configuration

1. Import the Git repository containing this project into Vercel.
2. Set the Vercel **Root Directory** to the directory containing `main.py`, `pyproject.toml`, `requirements.txt`, and the `app/` and `frontend/` folders.
3. Use Python 3.12. The repository includes `.python-version`.
4. The `pyproject.toml` entrypoint points Vercel to `main:app`.
5. Do not set a Uvicorn start command. Vercel's Python runtime loads the ASGI app.
6. Attach all three domains to this same Vercel project:
   - `ig-api.meridin.in`
   - `ig-app.meridin.in`
   - `ig-admin.meridin.in`
7. In the domain setup UI, use the exact DNS records Vercel provides. Do not guess CNAME targets or delete existing `meridin.in` records.

## Required Vercel environment variables

Set these in Vercel → Project → Settings → Environment Variables for **Production**. Add Preview/Development values separately only if you use those environments.

Required:
- `APP_ENV=production`
- `PUBLIC_BASE_URL=https://ig-api.meridin.in` (no trailing slash)
- `CORS_ORIGINS=https://ig-app.meridin.in,https://ig-admin.meridin.in,https://ig-api.meridin.in`
- `MONGODB_URI` = existing production MongoDB connection string
- `MONGODB_DB` = existing production database name
- `JWT_SECRET` = preserve the existing production signing secret
- `TOKEN_ENCRYPTION_KEY` = preserve the exact existing Fernet key
- `ADMIN_EMAIL` = existing platform admin email
- `ADMIN_PASSWORD` = existing secure platform admin password
- `LOG_LEVEL=INFO`

Also preserve and configure the existing optional variables if used:
- `LLM_ENABLED`, `LLM_BASE_URL`, `LLM_API_STYLE`, `LLM_API_KEY`, `LLM_MODEL`
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_BASE_URL`
- `VISUAL_SEARCH_ENABLED` and related CLIP settings only if the optional vision dependencies are installed and used.

Never put secret values in Git, source files, ZIP files, or chat. Do not regenerate `JWT_SECRET` or `TOKEN_ENCRYPTION_KEY` during this domain migration. Rotating `TOKEN_ENCRYPTION_KEY` without a migration would make already-encrypted customer Meta secrets and Instagram tokens unreadable.

## Database and serverless notes

- Use the existing managed MongoDB deployment. Ensure its network access rules permit the Vercel runtime. Do not expose database credentials in client-side JavaScript.
- Vercel Functions are serverless. In-memory state is not durable and can differ between instances. This app's durable state must remain in MongoDB / R2.
- Vercel may create multiple function instances. Review MongoDB connection counts and Atlas limits under load.
- Do not use local filesystem storage for customer uploads; use the configured R2 object storage.
- Confirm the app starts successfully and that the MongoDB ping and index initialization complete in Vercel runtime logs.
- Webhook processing must complete within the configured Vercel Function duration. Monitor function duration and Meta delivery retries.
- If you later add long-running background jobs, persistent workers, or sustained queue consumers, use a worker-capable host rather than assuming a serverless function stays alive.

## Meta configuration after changing the API domain

This code version generates each customer's webhook callback URL as:

`https://ig-api.meridin.in/webhooks/instagram/{CLIENT_ID}`

The actual client-specific URL is shown in that customer's dashboard → Instagram integration / Meta configuration section. Copy that exact URL into the customer's Meta Developer App → Webhooks → Instagram callback URL.

- Keep each customer's existing Verify Token unchanged and make sure it matches the value saved in the Meridin client configuration.
- If Meta requires webhook verification again after the URL change, verify the new callback using the same verify token.
- The uploaded code uses customer-specific webhook callbacks and manual token configuration. It does not define an OAuth redirect URI in the inspected routes, so do not invent or register an OAuth redirect URI for this build.
- Keep existing App IDs, App Secrets, access tokens, permissions, and subscriptions. Change only the callback URL where required.
- Keep the old callback registered during migration if Meta allows it; remove it only after the new callback has been verified and real message delivery is confirmed.

## Production verification

Check these URLs:

1. `https://ig-api.meridin.in/health` — health endpoint; confirm expected JSON and database availability.
2. `https://ig-app.meridin.in/` — should redirect to `/dashboard/` and show the client login.
3. `https://ig-admin.meridin.in/` — should redirect to `/admin/` and show the admin login.
4. `https://ig-api.meridin.in/docs` — API docs, if enabled for the deployment.

Then test:
- Client login and admin login separately.
- Browser Network tab: dashboard `/api/...` requests should return from the same dashboard hostname and not fail with 404/500.
- Catalogue read/write and product image upload to R2.
- Client Meta config displays the new `ig-api` webhook callback.
- Meta webhook verification GET and real incoming DM POST.
- Message response delivery and duplicate webhook handling.
- Vercel function logs and MongoDB connectivity.

A successful homepage or `/health` response alone does not establish production readiness.
