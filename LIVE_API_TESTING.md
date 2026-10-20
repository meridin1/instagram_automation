# Test the deployed Meridin API safely

This helper calls the existing authenticated `POST /api/test/inbound` endpoint. That endpoint runs the real message-processing service with `send_to_instagram=False`: replies are not sent to Instagram, but test messages/conversations ARE stored in the selected tenant's MongoDB. Use a dedicated test workspace.

## Windows PowerShell

1. Open the project folder and activate your Python environment.
2. Install project dependencies (`pip install -r requirements.txt`) if not already installed.
3. Sign in to the test client through `/api/auth/login` or `/docs` and copy its JWT access token. Treat it like a password; do not paste it into chat or commit it.
4. Set environment variables in the same PowerShell window:

```powershell
$env:MERIDIN_API_BASE = "https://YOUR-RENDER-SERVICE.onrender.com"
$env:MERIDIN_API_TOKEN = "PASTE_TEST_CLIENT_JWT_HERE"
python scripts/live_api_test.py --confirm-write
```

For local testing, use `http://127.0.0.1:8000` as the base URL.

The script checks `/health`, sends six realistic text messages to the authenticated test endpoint, prints the actual intent/entities/reply, and writes a JSON report. It returns a non-zero exit code if an asserted intent or HTTP/reply check fails. Some intents are deliberately observational rather than hard assertions, so inspect those replies manually.

## Important limits

- The script writes test conversations and messages to MongoDB. The `--confirm-write` flag is required as a safety check.
- It does not send Instagram replies.
- It does not test actual Meta webhooks, image attachments, OAuth, or live Instagram delivery. Use `INSTAGRAM_REAL_ACCOUNT_TESTING.md` for that separate phase.
- Run only against a workspace/catalogue you control.
