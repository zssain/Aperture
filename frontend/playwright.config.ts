import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command:
        "zsh -c 'export DATABASE_URL=${E2E_DATABASE_URL:-postgresql+asyncpg://postgres@127.0.0.1:55432/aperture_test}; export SESSION_COOKIE_SECURE=false; uv run alembic -x db_url=$DATABASE_URL upgrade head; uv run python -m tests.e2e_seed; uv run python -m app.worker & aperture_worker=$!; trap \"kill $aperture_worker\" EXIT; uv run uvicorn app.main:app --host 127.0.0.1 --port 8000'",
      cwd: "../backend",
      url: "http://127.0.0.1:8000/api/v1/health",
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4173",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: true,
    },
  ],
});
