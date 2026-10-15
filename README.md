# Meridin Instagram Automation — Client-ready MVP

This project is a production-oriented MVP for Instagram DM automation for clothing/fashion sellers.

## Included features

1. Client management
2. Catalogue/product CRUD
3. Stock and quantity
4. Product -> Instagram media mapping
5. Rule + ML intent classification
6. Entity extraction
7. English + Manglish/Malayalam rule coverage
8. LLM structured fallback
9. Safe server-side LLM tools
10. Database-backed responses
11. Conversation context
12. Human takeover/resume
13. JWT authentication
14. Tenant isolation
15. Instagram account management
16. Meta OAuth flow
17. Instagram webhook verification/signature handling
18. Duplicate message protection
19. Semantic catalogue search
20. Functional web dashboard

## Architecture

Instagram -> Meta webhook -> FastAPI -> normalization -> rules/ML -> entity extraction -> conversation context -> catalogue filters/semantic search -> deterministic response or validated LLM fallback -> Instagram.

The catalogue is the source of truth. The LLM is never trusted for price, stock, sizes, colours, product links, delivery policy, or business policy.

## Requirements

Python 3.12 is recommended. MongoDB 7+ or MongoDB Atlas is required.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set at least:

```env
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=meridin_instagram
JWT_SECRET=<long-random-secret>
META_VERIFY_TOKEN=<random-webhook-token>
```

For LLM:

```env
LLM_ENABLED=true
LLM_API_KEY=<provider-key>
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
```

Any OpenAI-compatible `/chat/completions` provider can be used if it supports JSON response format.

Run:

```powershell
uvicorn app.main:app --reload --port 8000
```

Open:
- http://localhost:8000/docs
- http://localhost:8000/dashboard/
- http://localhost:8000/health

## First client

1. Register at `/dashboard/`.
2. Add business information.
3. Add catalogue products.
4. Reindex catalogue from `/docs` using `POST /api/search/reindex`.
5. Enable LLM only after setting the server LLM credentials.
6. Connect Instagram with the Meta OAuth button.
7. Configure the Meta webhook to `https://YOUR_DOMAIN/webhooks/instagram`.
8. Use the Meta webhook verification token from `.env`.
9. Test real DMs.

## Security

- Client ID is derived from the JWT for authenticated APIs.
- Every tenant-owned database query includes client_id.
- Passwords use Argon2 through pwdlib.
- JWTs are signed server-side.
- Instagram access tokens are never returned by the account-list API.
- Webhook HMAC verification is enabled when META_APP_SECRET is configured.
- `.env` is ignored by git.

## LLM safety

The LLM returns a constrained structured understanding object. Server code then executes catalogue/business tools. The model cannot directly write catalogue facts into a response.

Known flows are deterministic. LLM is used for ambiguous language and search interpretation.

## Production

Run behind HTTPS and a reverse proxy/load balancer. Use MongoDB Atlas or a managed MongoDB deployment. Set a strong JWT secret, Meta credentials, LLM credentials, restrictive CORS origins, and production logging/monitoring.

The Meta API scopes/endpoints can change over time. Configure the scopes and Graph version supported by the Meta product enabled in your developer application. The code keeps these values in environment variables instead of hardcoding a tutorial-specific version.
