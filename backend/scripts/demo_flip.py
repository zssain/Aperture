"""Fire the verified-income demo events at a declined applicant (default: APL-1076).

Signs in as the demo analyst, posts the feature-gated income-consistency events, then
waits for the redecision job to land and reports the decision change. This is the
stage-safe way to trigger the "newly eligible" moment without hand-typing a curl.

Usage:  uv run python scripts/demo_flip.py [applicant_ref]
"""

import sys
import time

import httpx

BASE = "http://localhost:8000/api/v1"
EMAIL = "credit-analyst@demo.aperture.test"
PASSWORD = "Demo-Only-Strong-Passw0rd!"


def main() -> None:
    applicant_ref = sys.argv[1] if len(sys.argv) > 1 else "APL-1076"
    with httpx.Client(base_url=BASE, timeout=30) as client:
        login = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        login.raise_for_status()
        # The session cookie is Secure; cookiejars refuse to replay it over plain
        # http://localhost (browsers exempt localhost), so attach cookies by hand.
        cookies = {
            name: value
            for header in login.headers.get_list("set-cookie")
            for name, _, value in [header.split(";", 1)[0].partition("=")]
        }
        csrf = cookies.get("aperture_csrf")
        if csrf is None:
            raise SystemExit("no CSRF cookie issued at login")
        client.headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {"X-CSRF-Token": csrf}

        fired = client.post(
            "/demo/events/income-consistency",
            json={"applicant_ref": applicant_ref},
            headers=headers,
        )
        if fired.status_code == 404:
            raise SystemExit(
                "demo endpoint is disabled — set DEMO_EVENTS_ENABLED=true and restart the API"
            )
        fired.raise_for_status()
        body = fired.json()
        job_id = body.get("job_id")
        print(f"Fired {len(body['event_ids'])} verified income events at {applicant_ref}.")
        if job_id is None:
            print("No redecision job was queued (was one already pending?).")
            return

        print(f"Waiting for redecision job {job_id} …")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = client.get(f"/jobs/{job_id}")
            job.raise_for_status()
            status = job.json()["status"]
            if status in {"SUCCEEDED", "FAILED", "DEAD"}:
                print(f"Job {status}.")
                if status == "SUCCEEDED":
                    print(
                        f"{applicant_ref} has been re-decided — open the queue's "
                        "'Newly eligible' view."
                    )
                return
            time.sleep(1)
        print("Job still running after 60s — check the worker is up (make dev runs one).")


if __name__ == "__main__":
    main()
