import { probeBackendHealth } from "./systemHealth";

describe("systemHealth", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("probes the relative API route by default so Vite can proxy it in dev", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          api: true,
          profile_path_configured: true,
          template_configured: true,
        }),
        { status: 200 },
      ),
    );

    const result = await probeBackendHealth();

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/health",
      expect.objectContaining({
        method: "GET",
      }),
    );
    expect(result.status).toBe("healthy");
  });

  it("builds the probe URL from an explicit API base URL when provided", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true, api: true }), { status: 200 }),
    );

    await probeBackendHealth({ baseUrl: "http://localhost:8000/" });

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://localhost:8000/api/health",
      expect.objectContaining({
        method: "GET",
      }),
    );
  });
});
