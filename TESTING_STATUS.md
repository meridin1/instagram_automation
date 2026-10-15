# Testing status for this package

## Checks completed in the packaging environment

- Python source compilation: PASS (`python -m compileall -q app scripts`).
- Python AST parse across `app/**/*.py`: PASS.
- Client dashboard JavaScript syntax: PASS (`node --check frontend/client/assets/app.js`).
- Admin dashboard JavaScript syntax: PASS (`node --check frontend/admin/assets/app.js`).
- Added tests for OAuth authorization-code grant, Instagram Login `/me/subscribed_apps` path, and safe replies to attachment-only messages.

## Checks not completed here

- `pytest`: BLOCKED before test execution because this environment does not have project dependencies installed (`motor`, `pwdlib`, `bson`/PyMongo). Attempting to download dependencies failed because package network access is unavailable. This is not a passing pytest result.
- MongoDB integration: NOT RUN; no project MongoDB URI/database is available in this packaging environment.
- Real Meta OAuth, webhook subscription, inbound DM, and outbound reply: NOT RUN; these require the user's Meta app credentials, public HTTPS deployment, approved/tester account setup, and a live Instagram Professional account.
- Live LLM calls: NOT RUN; require a valid configured provider key/model and network access.

## Required next command on the user's Windows machine

```powershell
python -m pip install -r requirements.txt
python -m compileall -q app scripts
node --check frontend/client/assets/app.js
node --check frontend/admin/assets/app.js
pytest -q app/tests
python scripts/smoke_test.py
```

If a test fails, capture the complete traceback and send it back before attempting real Instagram connection. Then follow `INSTAGRAM_REAL_ACCOUNT_TESTING.md` for the live integration phase.
