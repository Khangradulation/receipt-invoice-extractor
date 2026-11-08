import { config } from './config';

/** Error shape returned by the API (see receipt_shared.http.ErrorResponse). */
export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string | null };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;

  constructor(status: number, code: string, message: string, requestId: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as ApiErrorBody).error?.message === 'string'
  );
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /** Bearer token; wired to Firebase Auth in Phase 7/8. */
  token?: string | null;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, token, headers, ...rest } = options;
  const finalHeaders = new Headers(headers);
  finalHeaders.set('Accept', 'application/json');
  if (body !== undefined) finalHeaders.set('Content-Type', 'application/json');
  if (token) finalHeaders.set('Authorization', `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      ...rest,
      headers: finalHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'network_error', 'Unable to reach the server. Check your connection.');
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    if (isApiErrorBody(data)) {
      throw new ApiError(
        response.status,
        data.error.code,
        data.error.message,
        data.error.request_id,
      );
    }
    throw new ApiError(response.status, `http_${response.status}`, response.statusText || 'Error');
  }
  return data as T;
}

export interface HealthResponse {
  status: 'ok';
  service: string;
  version: string;
  environment: string;
  timestamp: string;
}

export const api = {
  health: () => apiRequest<HealthResponse>('/api/v1/health'),
};
