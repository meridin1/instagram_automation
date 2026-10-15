# Customer-owned Meta app onboarding (Meridin)

This build stores Meta/Instagram app settings per Meridin workspace. The Admin Portal no longer owns a global customer Meta configuration. Each client enters their own app settings at Client Portal → Instagram integration.

## New customer checklist

1. Create a Meridin workspace using the client portal's **Create one** link. Sign in.
2. Ensure the Instagram account is a **Professional** account (Business or Creator). Keep access to the account and its owner Meta/Facebook account.
3. Visit https://developers.facebook.com/ and sign in using the customer's own Meta/Facebook account. Complete Meta Developer registration if prompted.
4. Create a Meta app. In the app's use cases/products, choose the current Instagram API setup with **Instagram Login / Business Login** and enable Instagram messaging. Dashboard wording can vary.
5. In the Instagram API setup with Instagram Login section, copy the **Instagram App ID** and the corresponding **Instagram App Secret** into the Client Portal form. These are used for Instagram OAuth.
6. In **App settings → Basic**, copy the **Meta App Secret** into the separate “Meta App Secret (webhook signature)” field. Do not confuse it with the Instagram-specific App Secret; if Meta's dashboard labels differ, follow the credentials shown for the exact login product you selected.
7. In Client Portal → Instagram integration, create a unique Webhook Verify Token (any sufficiently random private string), fill the credentials, and click **Save Meta app settings**. The token is not displayed again by the API after saving; copy it before leaving the page. If lost, enter a new token, save, and update Meta with the new token.
8. Copy the **OAuth callback / redirect URI** displayed in the Client Portal and add it exactly to the OAuth redirect URI allowlist in the Instagram Login settings in Meta Developers. Scheme, hostname, path, and trailing slash must match.
9. Copy the **Customer-specific Webhook Callback URL** from the portal. In the Instagram Webhooks configuration for that Meta app, paste it as Callback URL and paste the same Verify Token you saved in Meridin. Save and complete Meta's verification. Subscribe to the `messages` webhook field (and other fields only if used).
10. In Meta app settings, add the app's required website/privacy-policy details and configure the required permissions. During development, the connecting Instagram account/user may need to be added as an app role/tester. For customers who are not app roles, production use generally requires the appropriate permissions and Meta App Review/Advanced Access.
11. Return to Meridin → Instagram integration and click **Connect with Instagram**. Log in as the owner of the actual Instagram Professional account and approve the requested permissions. The backend obtains and stores the access token encrypted; do not paste an access token or Instagram password into the form.
12. Click **Enable messaging** if shown. Test by sending a DM from a separate Instagram account.

## What to copy where

| Value | Source | Destination |
|---|---|---|
| Instagram App ID | Meta Developers → Instagram API setup with Instagram Login | Client Portal → Instagram App ID |
| Instagram App Secret | Same Instagram Login setup | Client Portal → Instagram App Secret (OAuth exchange) |
| Meta App Secret | Meta Developers → App settings → Basic | Client Portal → Meta App Secret (webhook signature) |
| Webhook Verify Token | Create in the Client Portal (unique random value) | Paste the exact same value into Meta's webhook setup |
| OAuth callback URI | Displayed in Client Portal | Paste into Meta's OAuth redirect URI allowlist |
| Webhook callback URL | Displayed in Client Portal; unique to this workspace | Paste into Meta's webhook callback URL |
| Access token / Instagram user ID | Obtained by backend through OAuth | **Do not copy manually**; stored against this workspace |

## Production notes

- Set `PUBLIC_BASE_URL` in Render to the exact public HTTPS origin for the running Meridin API (for example `https://your-service.onrender.com`, with no trailing slash). Redeploy after changing it. This is used to generate the callback and webhook URLs.
- Keep `TOKEN_ENCRYPTION_KEY` stable. Changing it can make already-encrypted client secrets and account tokens unreadable.
- Every customer must configure their own app, redirect URI, webhook callback, and verify token. Webhook requests are routed through a URL containing the Meridin workspace ID, and signature validation uses only that workspace's configured secrets.
- The `messages` permission and actual account access are still subject to Meta's current API eligibility, app mode, and review requirements. A successful OAuth redirect alone does not prove webhooks or outbound replies work. Run the real-account checklist after setup.
