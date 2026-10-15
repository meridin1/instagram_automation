# Instagram integration onboarding

Each Meridin customer owns and configures their own Meta Developer app. The Client Portal → Instagram integration page contains the fields for that customer. The Admin Portal does not hold a shared customer Meta app.

Use `CUSTOMER_META_APP_SETUP.md` as the authoritative step-by-step guide. It explains where to find the Instagram App ID, Instagram App Secret, Meta App Secret, which callback URLs to copy into Meta, how to set the webhook verify token, and how to connect the customer's existing Instagram Professional account through OAuth.

App credentials and OAuth access tokens are encrypted in MongoDB and scoped by `client_id`. The client-facing API returns only secret-set indicators, never plaintext saved secrets or access tokens. Do not put app secrets or tokens in frontend JavaScript, Git, screenshots, or logs. Keep `TOKEN_ENCRYPTION_KEY` stable.
