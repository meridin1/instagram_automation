# Meta configuration storage

This version uses customer-owned Meta apps, not a shared platform Meta app. Customer settings are stored in MongoDB `client_meta_configs`, keyed by the authenticated Meridin `client_id`. OAuth and webhook secrets are Fernet-encrypted; the API returns only flags indicating whether each secret is saved.

Client API endpoints:
- `GET /api/clients/meta-config` returns the customer's public configuration and generated callback URLs.
- `PUT /api/clients/meta-config` saves that authenticated customer's configuration.

The Admin Portal has no Meta credential form. Follow `CUSTOMER_META_APP_SETUP.md` for the complete new-customer flow. Keep `TOKEN_ENCRYPTION_KEY` stable. Existing records in the old `platform_settings` collection are not used by this per-customer flow.
