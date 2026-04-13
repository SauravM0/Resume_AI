const DEFAULT_API_BASE_URL = "";
const API_BASE_URL = normalizeApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL,
);

let hasLoggedFirstApiRequest = false;

export function getApiBaseUrl(explicitBaseUrl?: string): string {
  return normalizeApiBaseUrl(explicitBaseUrl ?? API_BASE_URL);
}

export function buildApiUrl(pathname: string, explicitBaseUrl?: string): string {
  const normalizedPath = pathname.startsWith("/") ? pathname : `/${pathname}`;
  const apiBaseUrl = getApiBaseUrl(explicitBaseUrl);
  const resolvedUrl = `${apiBaseUrl}${normalizedPath}`;

  logFirstResolvedApiRequest(apiBaseUrl, resolvedUrl);

  return resolvedUrl;
}

function normalizeApiBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, "");
}

function logFirstResolvedApiRequest(apiBaseUrl: string, resolvedUrl: string) {
  if (!import.meta.env.DEV || hasLoggedFirstApiRequest) {
    return;
  }

  hasLoggedFirstApiRequest = true;
  console.debug("[api] resolved base URL", {
    apiBaseUrl,
    requestUrl: resolvedUrl,
  });
}
