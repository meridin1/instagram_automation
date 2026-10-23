# Meridin Instagram Automation — clean test start

This package fixes the authentication contract used by the API, Swagger, and dashboard.

## 1. Start the project

PowerShell:

```powershell
cd C:\Users\Admin\Desktop\meridin-instagram-phase1
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

If your virtual environment is named `.venv312`, activate that instead.

## 2. Check health

Open:

`http://127.0.0.1:8000/health`

Expected:

```json
{"status":"ok"}
```

## 3. Register a fresh development account

Use `POST /api/auth/register` in Swagger with:

```json
{
  "brand_name": "Test Clothing",
  "email": "test@example.com",
  "password": "test1234",
  "instagram_username": "test_clothing",
  "business_information": "Women's clothing store",
  "location": "Kasaragod, Kerala",
  "delivery_information": "Delivery available across Kerala",
  "business_hours": "10 AM - 8 PM",
  "language": "English",
  "tone": "Friendly",
  "automation_enabled": true,
  "llm_enabled": false
}
```

The API returns `201` and an access token.

## 4. Test login independently

Use a second PowerShell window:

```powershell
$body = @{
    username = "test@example.com"
    password = "test1234"
}

Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/api/auth/login" `
    -Method POST `
    -ContentType "application/x-www-form-urlencoded" `
    -Body $body
```

Expected fields:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "client_id": "..."
}
```

## 5. Test Swagger authorization

Open `http://127.0.0.1:8000/docs`, click **Authorize**, and enter:

- Username: `test@example.com`
- Password: `test1234`
- Client ID: leave empty
- Client secret: leave empty

Swagger sends the OAuth2 password request as form data. Do not send JSON to `/api/auth/login`.

## 6. Test a protected endpoint

After authorization, call:

`GET /api/auth/me`

It should return the authenticated user without `password_hash`.

Then test:

- `GET /api/clients/me`
- `GET /api/products`
- `POST /api/products`
- `POST /api/test/inbound`

## 7. Test product automation

Create:

```json
{
  "name": "Floral Kurti",
  "sku": "FLORAL-KURTI-001",
  "price": 1299,
  "category": "kurti",
  "description": "Floral printed cotton kurti",
  "sizes": ["S", "M", "L", "XL"],
  "colors": ["Pink", "Black", "Blue"],
  "stock": true,
  "quantity": 10,
  "product_url": "https://example.com/floral-kurti",
  "image_url": "",
  "active": true
}
```

Then call `POST /api/test/inbound` with:

```json
{
  "sender_id": "customer_001",
  "text": "ee dress inte price ethra?"
}
```

The endpoint derives the `client_id` from the JWT. Do not put another client's ID in the request.

## Authentication contract

- Registration accepts `brand_name` and also accepts legacy `name`.
- Login accepts OAuth2 form fields `username` and `password`.
- `create_access_token(user_id, client_id)` has one stable signature.
- Passwords are hashed and verified with the same `pwdlib.PasswordHash` instance.
- JWT contains `sub`, `client_id`, and `exp`.
- Protected routes derive tenant/client identity from the verified JWT.

## Signup approval workflow (latest update)

New client signups now create a pending application rather than an immediately usable account. Open `/admin` and select **Applications** to review it. Approve creates the client workspace and owner login; Reject removes the pending application. A repeated signup with the same pending email returns a pending message and does not create another application/notification. See `SIGNUP_APPROVAL_WORKFLOW.md` for details.

Voice-note replies/transcription are not part of this update. Existing tiered intent handling and optional CLIP-based image matching remain in the codebase.
