import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    os.getenv("WSW_INTEGRATION", "0") not in ("1", "true", "yes"),
    reason="Integration test requires Postgres + running Docker. Set WSW_INTEGRATION=1 to enable.",
)
def test_seed_and_validate_200k_smoke() -> None:
    """
    Minimal DB integration smoke test:
    - Runs the V8 seeder for a small target in CI-like environments by overriding target.
    - Validates that the script exits 0.

    Note: full 200,000 materialization is intentionally not run in CI by default.
    """
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = os.path.join(repo, "backend", "scripts", "seed_universe_v8.py")

    env = dict(os.environ)
    # Must point to Postgres; seed script will fail fast otherwise.
    assert env.get("DATABASE_DSN_ASYNC") or env.get("DATABASE_URL")

    # Use a smaller target to keep runtime bounded in CI.
    target = env.get("WSW_INTEGRATION_TARGET", "5000")

    cp = subprocess.run(
        [sys.executable, script, "--target", str(target), "--batch", "2000", "--verify", "--ci", "--concurrency", "2"],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if cp.returncode != 0:
        raise AssertionError(f"Seeder failed (exit={cp.returncode}). Output:\n{cp.stdout}")

