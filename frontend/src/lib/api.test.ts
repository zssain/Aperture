import { afterEach, beforeEach } from "vitest";

import { ApiError, request, setUnauthorizedHandler } from "./api";

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("api client", () => {
  beforeEach(() => setUnauthorizedHandler(null));
  afterEach(() => {
    vi.unstubAllGlobals();
    setUnauthorizedHandler(null);
  });

  it("on 401 calls the unauthorized handler with the return URL and throws ApiError", async () => {
    window.history.pushState({}, "", "/cases/42?tab=evidence");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: { code: "SESSION_EXPIRED", message: "expired" } }, 401),
      ),
    );

    await expect(request("/api/v1/protected")).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledWith("/cases/42?tab=evidence");
  });

  it("suppresses the unauthorized handler when requested (session probe)", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: { code: "X" } }, 401)),
    );

    await expect(
      request("/api/v1/auth/me", { suppressUnauthorized: true }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(handler).not.toHaveBeenCalled();
  });

  it("turns a network failure into a NETWORK_ERROR ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    await expect(request("/api/v1/x")).rejects.toMatchObject({
      code: "NETWORK_ERROR",
      status: 0,
    });
  });

  it("maps FastAPI validation errors into fieldErrors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: [{ loc: ["body", "email"], msg: "invalid" }] }, 422),
      ),
    );
    try {
      await request("/api/v1/x");
      throw new Error("expected ApiError");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).fieldErrors?.email).toEqual(["invalid"]);
    }
  });
});
