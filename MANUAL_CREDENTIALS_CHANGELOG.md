# Manual Instagram credentials update

This package replaces Instagram OAuth account authorization with manual credential entry.

## Client Portal changes
- Removed the Instagram OAuth connect button, OAuth callback/redirect settings, authorization URLs and scopes.
- Added fields for Instagram App ID, Meta App Secret, optional separate Instagram App Secret, webhook verify token, Graph API URL/version, and customer-specific webhook URL.
- Added a manual account form for Instagram Professional Account ID, username, and access token.
- Existing clients can leave the access-token field blank to retain their stored token; new connections require a token.
- Added an Enable messaging action after credentials are saved.

## Backend changes
- Removed `/api/instagram/connect` and `/api/instagram/oauth/callback` routes and Instagram OAuth code exchange helpers.
- `/api/instagram/accounts` now accepts manual account credentials and encrypts the access token before storing it.
- Existing workspace isolation remains enforced by authenticated `client_id`; the same Instagram account cannot be assigned to a different workspace.
- Secrets are never returned by the account listing/config endpoints.
- Webhook verification continues to use the customer-specific URL `/webhooks/instagram/{client_id}` and the customer's configured verify token/app secret.

## Verification performed
- Python compilation: passed.
- Client and admin JavaScript syntax checks: passed.
- Focused Instagram tests: 6 passed.
- Full test suite and real Meta/MongoDB tests were not completed in this packaging environment; see `TESTING_STATUS.md`.
