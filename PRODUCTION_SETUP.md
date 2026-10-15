# Meridin Instagram Automation — Production Setup

## Surfaces
- Client dashboard: `/dashboard/`
- Admin panel: `/admin/`
- API docs: `/docs`
- Health: `/health`
- Instagram webhook: `/webhooks/instagram`

## Required environment
Set at least:
- `MONGODB_URI`
- `MONGODB_DB`
- `JWT_SECRET` — long random secret
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `META_VERIFY_TOKEN`
- `META_APP_SECRET`
- `META_OAUTH_CLIENT_ID`
- `META_OAUTH_CLIENT_SECRET`
- `META_OAUTH_REDIRECT_URI`

Keep Meta secrets and the admin password only in the server environment.

## Client flow
1. Client registers or an admin creates the client.
2. Client logs in at `/dashboard/`.
3. Client enters business settings and catalogue.
4. Client connects Instagram with Meta OAuth.
5. Client subscribes the connected account to messaging from the dashboard.
6. Configure Meta webhook callback as `https://YOUR_API_HOST/webhooks/instagram`.
7. Configure the verify token to exactly match `META_VERIFY_TOKEN`.
8. Use Meta's webhook test, then send a real DM from a separate Instagram account.

## Important Meta production requirements
The server can implement OAuth, signature verification, account subscription and message processing, but Meta-side app configuration, permissions, professional-account requirements, App Review and production access must still be completed in Meta's developer console.

## Admin
The first admin is bootstrapped at startup from `ADMIN_EMAIL` + `ADMIN_PASSWORD`. Do not put these credentials into frontend source code. The admin can create, disable/enable, and permanently delete client tenants.

## Tenant isolation
All client catalogue, conversations, messages, settings and Instagram-account operations are scoped by the authenticated `client_id`. Admin routes are separately protected by the `admin` role.
