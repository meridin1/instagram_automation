# Signup approval workflow

- Public signup creates one `signup_applications` document with a normalized, unique email and a password hash. It does not create a client workspace or user account yet.
- The signup page displays an application-pending message and does not issue a login token.
- Repeated signup attempts with the same pending email return the same pending status/message and do not create duplicate applications or admin notifications.
- The admin dashboard polls the pending-application endpoint, displays a badge and a toast when new applications arrive, and provides Approve/Reject actions.
- Approve provisions the client, owner user, business settings and automation settings. Login becomes available after approval.
- Reject deletes the pending application record; no client/user workspace is created. The email can submit a fresh application later.
- Application password material is hashed before storage and never returned by the admin API.

## API
- `POST /api/auth/register` — submit signup application
- `GET /api/admin/applications` — admin-only pending applications
- `POST /api/admin/applications/{application_id}/approve` — admin-only approval
- `POST /api/admin/applications/{application_id}/reject` — admin-only rejection

The dashboard notification is in-app polling (15 seconds), not email/SMS/browser push.
