# Meridin Instagram Automation — Render deployment and Meta URLs

This version removes the `sentence-transformers`/PyTorch dependency and uses tenant-scoped keyword catalogue search. It keeps the existing intent/entity models and API routes. Product search is lexical, not neural semantic search.

## A. Deploy the API on Render

1. Push this project to a GitHub repository. Do **not** upload `.env`, access tokens, MongoDB credentials, or local virtual environments. Keep `.env` ignored by Git.
2. Open https://dashboard.render.com/ and choose **New + → Web Service**.
3. Connect the GitHub repository containing this project and select the `main` branch (or your actual deployment branch).
4. Set:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
5. Add the environment variables below in Render → your service → **Environment**. Do not put secret values into Git or this ZIP.

Required environment variables:

- `APP_ENV` = `production`
- `MONGODB_URI` = your MongoDB Atlas connection string (ensure Atlas Network Access permits Render; prefer restricting access appropriately rather than leaving a database publicly open)
- `MONGODB_DB` = `meridin_instagram`
- `PUBLIC_BASE_URL` = the exact public Render API origin, e.g. `https://your-service.onrender.com` (no trailing slash); the client portal uses it to display each client's callback URLs
- `JWT_SECRET` = a long, unique random secret
- `TOKEN_ENCRYPTION_KEY` = a valid Fernet key; generate locally using `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `ADMIN_EMAIL` = the email you will use for the platform administrator
- `ADMIN_PASSWORD` = a strong unique administrator password
- `CORS_ORIGINS` = your actual Render API origin, e.g. `https://YOUR-SERVICE-NAME.onrender.com` (no trailing slash). If the dashboard is served by this same service, this origin is sufficient.
- `LOG_LEVEL` = `INFO`

Optional LLM variables, only if you want the global LLM feature enabled:
- `LLM_ENABLED` = `true` or `false`
- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_API_STYLE`

6. Click **Create Web Service** and wait for the first deployment to finish.
7. Copy the public URL shown on the Render service page. In the rest of this guide, replace `https://YOUR-SERVICE-NAME.onrender.com` with that exact URL.
8. Verify these links in a browser:
   - `https://YOUR-SERVICE-NAME.onrender.com/health` — expected JSON `{"status":"ok","service":"meridin-instagram"}` if MongoDB is reachable.
   - `https://YOUR-SERVICE-NAME.onrender.com/docs` — API documentation.
   - `https://YOUR-SERVICE-NAME.onrender.com/dashboard/` — client dashboard.
   - `https://YOUR-SERVICE-NAME.onrender.com/admin/` — platform admin dashboard.

## B. Customer-specific Meta app setup

Set Render's `PUBLIC_BASE_URL` to the exact deployed API origin, for example `https://your-service.onrender.com` (no trailing slash). Each customer configures their own Meta app from the Client Portal → Instagram integration page. The portal displays the OAuth callback URI and customer-specific webhook URL. Follow `CUSTOMER_META_APP_SETUP.md` for which credential comes from which Meta screen and where each value must be pasted. Do not put customer secrets into the Admin Portal or `.env`.

## D. Test and go live

1. In Meta Developers, subscribe the webhook to the message fields required by the app and complete the verification challenge.
2. Use Meta's webhook test tool. Then test from a separate Instagram account that can message the connected professional Instagram account.
3. Confirm the event arrives in Render logs and that a response is sent only when the tenant account is connected and automation is enabled.
4. Complete the required Meta permissions, app review, and access requirements before relying on this for customer accounts. A successful Render deploy alone does not grant Instagram messaging permissions.

## Troubleshooting

- **`/health` fails:** check Render logs and the MongoDB URI/network access.
- **OAuth redirect mismatch:** compare the registered redirect URI and the callback URI displayed in that customer’s Client Portal character for character.
- **Webhook verification fails:** use the customer-specific webhook callback URL displayed in that client’s portal, and ensure its verify token matches exactly.
- **Token decryption fails after a redeploy:** keep the same `TOKEN_ENCRYPTION_KEY`; do not rotate it after tokens have been saved unless you have a migration plan.
- **Dashboard API requests fail:** open the browser developer console and Render logs; verify dashboard requests use the same deployed origin and `CORS_ORIGINS` matches that origin.

## Important

Set `PUBLIC_BASE_URL` to your exact Render service URL before customers copy callback URLs into their Meta apps. If the public hostname changes, update this setting and re-register the callback URLs in each affected customer Meta app.
