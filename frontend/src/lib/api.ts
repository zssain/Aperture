/**
 * Typed fetch wrapper.
 *
 * - Sends cookies (credentials: "include") — auth is an HttpOnly session cookie.
 * - Generates and sends an `X-Correlation-ID` on every request and surfaces the one
 *   the server echoes back on errors.
 * - Parses failures into a typed {@link ApiError}.
 * - On 401 it clears the session and hands control to the registered unauthorized
 *   handler, which redirects to sign-in preserving the return URL.
 */

export type FieldErrors = Record<string, string[]>;
import { CSRF_HEADER, readCsrfToken } from "./csrf";

export interface ApiErrorShape {
  status: number;
  code: string;
  message: string;
  correlationId: string;
  fieldErrors?: FieldErrors;
}

export class ApiError extends Error implements ApiErrorShape {
  readonly status: number;
  readonly code: string;
  readonly correlationId: string;
  readonly fieldErrors?: FieldErrors;

  constructor(shape: ApiErrorShape) {
    super(shape.message);
    this.name = "ApiError";
    this.status = shape.status;
    this.code = shape.code;
    this.correlationId = shape.correlationId;
    this.fieldErrors = shape.fieldErrors;
  }
}

const CORRELATION_HEADER = "X-Correlation-ID";

export function generateCorrelationId(): string {
  const cryptoObj = globalThis.crypto;
  if (cryptoObj && typeof cryptoObj.randomUUID === "function") {
    return cryptoObj.randomUUID();
  }
  return `cid-${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
}

type UnauthorizedHandler = (returnTo: string) => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;

/** Register how a 401 is handled (clear session + redirect preserving return URL). */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

function currentReturnTo(): string {
  if (typeof window === "undefined") return "/";
  return `${window.location.pathname}${window.location.search}`;
}

interface RawErrorBody {
  detail?:
    | { code?: string; message?: string }
    | Array<{ loc?: Array<string | number>; msg?: string }>
    | string;
}

function parseError(
  status: number,
  correlationId: string,
  body: RawErrorBody | null,
  retryAfter?: string | null,
): ApiError {
  const detail = body?.detail;

  if (Array.isArray(detail)) {
    // FastAPI validation errors → field errors.
    const fieldErrors: FieldErrors = {};
    for (const item of detail) {
      const path = (item.loc ?? []).filter((p) => p !== "body").join(".") || "_";
      const messages = fieldErrors[path] ?? [];
      messages.push(item.msg ?? "Invalid value");
      fieldErrors[path] = messages;
    }
    return new ApiError({
      status,
      code: "VALIDATION_ERROR",
      message: "Please correct the highlighted fields.",
      correlationId,
      fieldErrors,
    });
  }

  if (detail && typeof detail === "object") {
    return new ApiError({
      status,
      code: detail.code ?? "ERROR",
      message: status === 429
        ? `${detail.message ?? "Too many requests."} Retry after ${retryAfter ?? "a short wait"} seconds.`
        : detail.message ?? "Something went wrong.",
      correlationId,
    });
  }

  return new ApiError({
    status,
    code: "ERROR",
    message: typeof detail === "string" ? detail : "Something went wrong.",
    correlationId,
  });
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  signal?: AbortSignal;
  /** Skip the global 401 handler — used by the session probe, where a 401 simply
   * means "not signed in" rather than "session expired mid-use". */
  suppressUnauthorized?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const correlationId = generateCorrelationId();
  const headers: Record<string, string> = {
    [CORRELATION_HEADER]: correlationId,
  };
  if (!options.formData) headers["Content-Type"] = "application/json";
  const method = options.method ?? "GET";
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = readCsrfToken();
    if (csrf) headers[CSRF_HEADER] = csrf;
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "include",
      headers,
      body: options.formData ??
        (options.body === undefined ? undefined : JSON.stringify(options.body)),
      signal: options.signal,
    });
  } catch {
    // Network failure — never a blank screen; callers render an ErrorState.
    throw new ApiError({
      status: 0,
      code: "NETWORK_ERROR",
      message: "Could not reach the server. Check your connection and retry.",
      correlationId,
    });
  }

  const serverCorrelationId = response.headers.get(CORRELATION_HEADER) ?? correlationId;

  if (response.status === 204) {
    return undefined as T;
  }

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    if (response.status === 401 && !options.suppressUnauthorized) {
      unauthorizedHandler?.(currentReturnTo());
    }
    throw parseError(
      response.status,
      serverCorrelationId,
      payload as RawErrorBody | null,
      response.headers.get("Retry-After"),
    );
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions): Promise<T> =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> =>
    request<T>(path, { ...options, method: "PATCH", body }),
  upload: <T>(path: string, formData: FormData, options?: RequestOptions): Promise<T> =>
    request<T>(path, { ...options, method: "POST", formData }),
};
