# Real Instagram integration and complete test checklist

This checklist is for the Instagram Login API (`graph.instagram.com`) used by this project. It requires a public HTTPS deployment for real Meta webhooks. `localhost` alone cannot receive production webhooks.

## A. Before testing

- [ ] Python 3.12 virtual environment is active.
- [ ] `pip install -r requirements.txt` completes successfully.
- [ ] MongoDB is reachable using `MONGODB_URI`.
- [ ] `.env` contains unique `JWT_SECRET` and a persistent `TOKEN_ENCRYPTION_KEY`. Each customer saves their own Meta app settings from Client Portal → Instagram integration.
- [ ] Client Portal has the Instagram App ID and Instagram App Secret for that customer's own Meta app.
- [ ] The Meta App Secret and webhook verify token are saved in that client's portal.
- [ ] The callback URL displayed in the portal exactly matches the URL registered in that customer's Meta app.
- [ ] The customer-specific webhook URL and verify token are configured in that customer's Meta app.
- [ ] The Instagram account is a Professional account (Business or Creator), not a personal account.

Generate secrets on Windows PowerShell:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep `TOKEN_ENCRYPTION_KEY` unchanged after tokens have been saved. If it changes, previously encrypted access tokens cannot be decrypted.

## B. Local automated checks

Run from the project root:

```powershell
python -m compileall -q app scripts
node --check frontend/client/assets/app.js
node --check frontend/admin/assets/app.js
pytest -q app/tests
python scripts/smoke_test.py
```

The full suite needs the dependencies in `requirements.txt`. These checks do not prove Meta connectivity; the real account flow in section E is separate.

## C. Dashboard functional tests (no real Instagram connection needed)

1. Start the app: `uvicorn app.main:app --reload --port 8000`.
2. Confirm `http://127.0.0.1:8000/health` returns `{"status":"ok"}`.
3. Open `/dashboard/`, register a test workspace, then sign out and sign in again.
4. Confirm Catalogue, Inbox, Instagram, and Settings load.
5. Add one test product; refresh and verify one new row appears. Each Add Product submission creates one product record by design.
6. Edit that product and confirm the same row changes rather than adding another row.
7. Configure business information and delivery policy in Settings, save, refresh, and confirm the values persist.
8. Use `/docs` to authorize with the same email/password and verify `/api/auth/me`, `/api/clients/me`, `/api/products`, and `/api/conversations`.
9. Test `/api/test/inbound` with a JWT and messages such as `ee dress inte price ethra?`, `black colour undo XL?`, `show me something under 1500`, and `I want to talk to a human`.
10. Confirm price/stock/size replies come from the catalogue; unknown or order/return requests are handed to a human according to settings.

## D. Meta developer dashboard setup

Meta's exact menu labels can change. In your Meta developer app:

1. Add/configure the Instagram API with Instagram Login product/use case.
2. Configure the OAuth redirect URL to match the saved OAuth redirect URI exactly.
3. Enable the `instagram_business_basic` and `instagram_business_manage_messages` permissions/scopes.
4. Add the Instagram account you will test with as an app tester/developer where required, then accept the invite from that account.
5. In the client portal, copy the customer-specific webhook callback URL. Configure Webhooks for Instagram and paste that URL.
6. Set the webhook verify token to exactly the value saved for this client in the Client Portal.
7. Subscribe to the `messages` webhook field (and `messaging_postbacks` if used by your app).
8. Make sure your reverse proxy sends the raw request body and `X-Hub-Signature-256` header unchanged to FastAPI.
9. Keep app secrets only on the server; never put them in dashboard JavaScript or browser storage.

For other people's accounts outside your app roles/testers, you may need App Review/Advanced Access and any business verification Meta requires. Passing development-mode tests does not prove general customer access.

## E. Connect a real account from the Meridin dashboard

1. Deploy the app behind HTTPS and set the production `.env` values before starting/restarting it.
2. Open `https://YOUR_PUBLIC_HOST/dashboard/` and sign in to the relevant Meridin workspace.
3. Open **Instagram** and click **Connect Instagram**.
4. Instagram's consent page should open. Sign in with the Professional account, review the requested permissions, and authorize.
5. You should return to the dashboard and see the connected username.
6. Click **Enable messaging**. The server should subscribe the connected account through the Instagram Login API.
7. In Meta's webhook tester, send a test event if available. Then, from a separate Instagram account, send a real text DM to the connected Professional account.
8. Confirm the webhook receives it, a conversation appears in Inbox, the message is stored once, and a reply appears in the sender's Instagram inbox.
9. Test a product question with a known product, a nonexistent product, a photo-only DM, and a voice-note DM. The current code does not perform image recognition or voice transcription: it asks the customer to type the product name/question instead of pretending to understand the media.
10. If the account token gets close to expiry, use **Refresh token** in the Instagram panel while the token is still eligible for refresh. Reconnect via OAuth if refresh fails.

## F. Diagnose common failures

- **Connect Instagram returns 503:** this workspace’s Meta app configuration is incomplete in Client Portal → Instagram integration.
- **OAuth redirect mismatch:** callback URL differs between Client Portal and Meta settings.
- **Token exchange fails:** check app ID/secret, exact redirect URI, `grant_type`, app product, and allowed account/tester status.
- **Connected account appears but DMs never arrive:** check public HTTPS reachability, the customer-specific saved Meta App Secret, webhook verification, `messages` field subscription, account messaging subscription, and whether the sender is allowed during development mode.
- **Webhook returns 403:** the verify token does not match on GET verification, or `X-Hub-Signature-256` does not match the raw request body and the customer-specific Meta App Secret.
- **DM is stored but no reply is sent:** inspect server logs for Graph API permission errors, token expiry, the recipient's Instagram-scoped ID, and whether automation is enabled.
- **`TOKEN_ENCRYPTION_KEY` changed:** restore the original key from secure storage; do not generate a new one against an existing database.

## Validation boundary

A successful `pytest` run and a local dashboard test are not equivalent to live Meta validation. Mark the deployment production-ready only after section E passes with the intended account type and permissions.
