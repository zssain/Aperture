"""Pre-demo smoke test: prove the live path actually works before you present.

This is the guard for the demo's biggest risk — a stale or dead job worker running
old code. The seeded book is decided inline, so it looks fine even when the worker is
broken; this check exercises the REAL worker path end-to-end and fails loudly if it is
not current and wired:

  1. API is up and login works.
  2. A live connect job runs through the worker to a committed decision.
  3. The decision is CLEAR / an approval — i.e. the mock-AA statement reconciles
     (the D5 fix is in the running worker, not just on disk).

Prints PASS/FAIL, cleans up its probe applicant, and exits non-zero on failure so it
can gate a rehearsal.

Usage:  uv run python scripts/demo_check.py
"""

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://localhost:8000/api/v1"
EMAIL = "credit-analyst@demo.aperture.test"
PASSWORD = "Demo-Only-Strong-Passw0rd!"


def _fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    started = time.monotonic()
    try:
        health = httpx.get(f"{BASE}/health", timeout=5)
    except httpx.HTTPError as exc:
        _fail(f"API not reachable on :8000 ({exc}). Is `make dev` running?")
    if health.status_code != 200:
        _fail(f"API health returned {health.status_code}")

    with httpx.Client(base_url=BASE, timeout=60) as client:
        login = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if login.status_code != 200:
            _fail(f"login failed ({login.status_code}). Run `make demo-reset` first.")
        cookies = {
            name: value
            for header in login.headers.get_list("set-cookie")
            for name, _, value in [header.split(";", 1)[0].partition("=")]
        }
        if "aperture_csrf" not in cookies:
            _fail("no CSRF cookie issued at login")
        client.headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        client.headers["X-CSRF-Token"] = cookies["aperture_csrf"]

        ref = f"PREFLIGHT-{int(started)}"
        created = client.post(
            "/applications",
            json={
                "display_name": "Preflight Probe",
                "external_ref": ref,
                "declared_income_paise": 5_000_000,
                "occupation": "SALARIED",
                "requested_amount_paise": 5_000_000,
                "requested_tenor_months": 12,
                "consent_granted": True,
                "purpose": "Preflight smoke test",
                "scope": ["BANK"],
                "expires_at": "2027-01-01T00:00:00Z",
            },
        )
        if created.status_code != 201:
            _fail(f"connect intake returned {created.status_code}: {created.text[:200]}")
        job_id = created.json().get("job_id")
        if job_id is None:
            _fail("connect intake queued no ingest job")

        deadline = time.monotonic() + 30
        job: dict[str, object] = {}
        while time.monotonic() < deadline:
            job = client.get(f"/jobs/{job_id}").json()
            if job["status"] in {"SUCCEEDED", "FAILED", "DEAD"}:
                break
            time.sleep(0.5)
        if job.get("status") != "SUCCEEDED":
            _fail(
                f"ingest job did not succeed (status={job.get('status')}). "
                "The worker is likely down or running stale code — restart `make dev` "
                "and kill any old `app.worker` processes."
            )

        # The stale-worker regression manifests as a fraud gate: the pre-fix mock AA
        # statement never reconciled, so D5 fired HIGH on every connect. The
        # affordability outcome varies with the randomly-assigned mock persona, so we
        # assert on the verification band, which must be CLEAR once the D5 fix is live.
        outcome = str((job.get("result") or {}).get("outcome"))
        rows = client.get("/queue", params={"view": "all-decisions", "q": ref}).json()
        row = next((r for r in rows.get("rows", []) if r.get("applicant_ref") == ref), None)
        if row is None:
            _fail("probe decided but did not appear in the queue")
        band = row.get("verification")
        if band != "CLEAR":
            _fail(
                f"live connect verification band is {band!r}, expected CLEAR. The worker "
                "is running the pre-fix mock AA (balances don't reconcile, D5 fires) — "
                "restart `make dev` and kill any stale `app.worker` processes."
            )

    print(
        f"PASS: live connect -> {outcome}, verification CLEAR, in "
        f"{time.monotonic() - started:.1f}s. Worker is current and the pipeline is wired."
    )
    print(f"(Probe applicant {ref} left in the book; `make demo-reset` clears it.)")


if __name__ == "__main__":
    main()
