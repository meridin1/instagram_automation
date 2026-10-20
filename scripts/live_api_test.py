"""Run safe, text-only test conversations against Meridin's authenticated /api/test/inbound.

Required environment variables:
  MERIDIN_API_BASE=https://your-deployment.example
  MERIDIN_API_TOKEN=<JWT access token> (optional if email/password are supplied)
  MERIDIN_API_EMAIL=<dedicated test-client email>
  MERIDIN_API_PASSWORD=<dedicated test-client password>

This endpoint writes test messages/conversations to the selected tenant's MongoDB,
but passes send_to_instagram=False so it does NOT send replies to Instagram customers.
Use a dedicated test client/workspace, and pass --confirm-write to proceed.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

CASES = [
    {"name": "Manglish price", "sender": "price-flow", "text": "ee dress inte price ethra?", "expected_intent": "product_price"},
    {"name": "Follow-up colour and size", "sender": "attributes-flow", "text": "black colour undo XL?", "expected_intent": None},
    {"name": "Alternative designs", "sender": "alternatives-flow", "text": "vere design undo?", "expected_intent": "product_alternatives"},
    {"name": "Human handoff", "sender": "handoff-flow", "text": "I want to talk to a human", "expected_intent": "human_handoff"},
    {"name": "Budget product search", "sender": "budget-flow", "text": "show me something under 1500", "expected_intent": "product_search"},
    {"name": "Malayalam/Manglish availability", "sender": "availability-flow", "text": "blue kurti undo?", "expected_intent": None},
]


def request_json(url, token=None, payload=None, timeout=45):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try: body = json.loads(raw)
            except json.JSONDecodeError: body = {"raw": raw[:2000]}
            return response.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try: body = json.loads(raw)
        except json.JSONDecodeError: body = {"raw": raw[:2000]}
        return exc.code, body


def login_for_token(base, email, password):
    """Fetch a fresh token so test runs do not fail because a copied JWT expired."""
    body = urllib.parse.urlencode({"username": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        base + "/api/auth/login", data=body,
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
            return payload.get("access_token"), None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try: detail = json.loads(raw)
        except json.JSONDecodeError: detail = raw[:1000]
        return None, f"Login failed (HTTP {exc.code}): {detail}"
    except Exception as exc:
        return None, f"Login failed: {exc}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-write", action="store_true", help="Confirm that test messages will be written to MongoDB")
    parser.add_argument("--prefix", default="meridin-test", help="Prefix for synthetic sender IDs")
    parser.add_argument("--delay", type=float, default=0.4, help="Seconds between requests (default: 0.4)")
    args = parser.parse_args()

    base = os.getenv("MERIDIN_API_BASE", "").strip().rstrip("/")
    token = os.getenv("MERIDIN_API_TOKEN", "").strip()
    email = os.getenv("MERIDIN_API_EMAIL", "").strip()
    password = os.getenv("MERIDIN_API_PASSWORD", "")
    if not base or (not token and not (email and password)):
        print("Set MERIDIN_API_BASE and either MERIDIN_API_TOKEN or MERIDIN_API_EMAIL + MERIDIN_API_PASSWORD. Do not paste secrets into chat or commit them.", file=sys.stderr)
        return 2
    if email and password:
        token, login_error = login_for_token(base, email, password)
        if not token:
            print(login_error, file=sys.stderr)
            return 1
        print("Authenticated using a fresh login token.")
    if not args.confirm_write:
        print("Safety stop: /api/test/inbound writes test messages to the tenant database. Re-run with --confirm-write after selecting a test workspace.", file=sys.stderr)
        return 2
    if not base.startswith("https://") and "localhost" not in base and "127.0.0.1" not in base:
        print("Refusing non-HTTPS remote API URL. Use HTTPS for deployed APIs.", file=sys.stderr)
        return 2

    print(f"Checking {base}/health ...")
    code, health = request_json(base + "/health")
    print(f"Health: HTTP {code} {json.dumps(health, ensure_ascii=False)}")
    if code != 200 or not isinstance(health, dict) or health.get("status") != "ok":
        print("Health check failed; stopping before writing test data.", file=sys.stderr)
        return 1

    results = []
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for case in CASES:
        sender = f"{args.prefix}-{run_id}-{case['sender']}"
        payload = {"sender_id": sender, "text": case["text"], "source_type": "automated_test"}
        code, body = request_json(base + "/api/test/inbound", token, payload)
        reply = body.get("reply") if isinstance(body, dict) else None
        actual_intent = body.get("intent") if isinstance(body, dict) else None
        intent_ok = case["expected_intent"] is None or actual_intent == case["expected_intent"]
        passed = 200 <= code < 300 and isinstance(body, dict) and bool(reply) and intent_ok
        item = {
            "name": case["name"], "text": case["text"], "http_status": code,
            "expected_intent": case["expected_intent"], "actual_intent": actual_intent,
            "intent_check": "not asserted" if case["expected_intent"] is None else ("pass" if intent_ok else "fail"),
            "reply": reply, "status": body.get("status") if isinstance(body, dict) else None,
            "entities": body.get("entities") if isinstance(body, dict) else None,
            "conversation_id": body.get("conversation_id") if isinstance(body, dict) else None,
            "passed": passed, "error_body": None if 200 <= code < 300 else body,
        }
        results.append(item)
        print("\n" + ("PASS" if passed else "FAIL") + f" | {case['name']} | HTTP {code}")
        print("  customer:", case["text"])
        print("  intent:", actual_intent, "| entities:", json.dumps(item["entities"], ensure_ascii=False))
        print("  reply:", reply)
        if item["error_body"] is not None:
            print("  error:", json.dumps(item["error_body"], ensure_ascii=False))
        time.sleep(max(0, args.delay))

    report = {
        "base_url": base, "run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "passed": sum(bool(x["passed"]) for x in results), "total": len(results), "results": results,
    }
    out = Path(f"meridin-api-test-report-{run_id}.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSummary: {report['passed']}/{report['total']} passed")
    print(f"Report saved to: {out.resolve()}")
    print("Note: image uploads and real Instagram delivery are not tested by /api/test/inbound.")
    return 0 if report["passed"] == report["total"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
