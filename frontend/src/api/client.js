const API_ROOT = import.meta.env.VITE_API_BASE || "/api";

export class ApiError extends Error {
  constructor(message, { status = 0, code = "request_failed", details = {}, payload = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.payload = payload;
  }
}

export function readCookie(name) {
  const prefix = `${name}=`;
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length) || "";
}

export async function apiRequest(path, options = {}) {
  const {
    accessToken,
    method = "GET",
    body,
    signal,
    csrf = false,
    headers: suppliedHeaders = {}
  } = options;
  const headers = new Headers({ Accept: "application/json", ...suppliedHeaders });

  if (body !== undefined) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (csrf) {
    const csrfToken = readCookie("csrf_refresh_token");
    if (csrfToken) headers.set("X-CSRF-TOKEN", decodeURIComponent(csrfToken));
  }

  let response;
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      method,
      headers,
      credentials: "include",
      signal,
      body: body === undefined ? undefined : JSON.stringify(body)
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError("Could not reach Butterlane. Check your connection and try again.", {
      code: "network_error"
    });
  }

  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(payload?.error?.message || payload?.message || "The request could not be completed.", {
      status: response.status,
      code: payload?.error?.code || "request_failed",
      details: payload?.error?.details || {},
      payload
    });
  }

  return payload;
}

export function responseData(payload) {
  return payload?.data ?? payload;
}
