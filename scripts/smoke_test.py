"""
Post-deploy smoke tests for fn-api.

Usage:
  python scripts/smoke_test.py https://<func-app>.azurewebsites.net/api

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.
"""
import sys
import time
import urllib.request
import urllib.error
import json

ENDPOINTS = [
    ("/groups",      200, lambda b: "groups" in b),
    ("/predictions", [200, 404], None),          # 404 is valid before matchday 1
    ("/fixtures/1",  [200, 404], None),
    ("/accuracy",    [200, 404], None),
    ("/nonexistent", 404, None),
]

OK   = "\033[32mOK  \033[0m"
FAIL = "\033[31mFAIL\033[0m"


def get(base: str, path: str, retries: int = 5) -> tuple[int, bytes]:
    url = base.rstrip("/") + path
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            # 503 = Function App cold-starting; retry with backoff
            if e.code == 503 and attempt < retries - 1:
                wait = 15 * (attempt + 1)
                print(f"  503 cold-start on {path}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            return e.code, b""
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(5)
    return -1, b""


def check(label: str, ok: bool) -> bool:
    marker = OK if ok else FAIL
    print(f"  {marker}  {label}")
    return ok


def main():
    if len(sys.argv) < 2:
        print("Usage: python smoke_test.py <API_BASE_URL>")
        sys.exit(1)

    base = sys.argv[1]
    print(f"\nSmoke tests → {base}\n")
    passed = True

    for path, expected_status, body_check in ENDPOINTS:
        try:
            status, body = get(base, path)
        except Exception as e:
            passed &= check(f"GET {path}  →  ERROR: {e}", False)
            continue

        allowed = [expected_status] if isinstance(expected_status, int) else expected_status
        status_ok = status in allowed

        if status_ok and body_check is not None:
            try:
                parsed = json.loads(body)
                content_ok = body_check(parsed)
            except Exception:
                content_ok = False
            ok = status_ok and content_ok
            passed &= check(f"GET {path}  →  {status} + body shape", ok)
        else:
            passed &= check(f"GET {path}  →  {status} (expected {expected_status})", status_ok)

    print()
    if passed:
        print("All smoke tests passed.")
    else:
        print("One or more smoke tests FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
