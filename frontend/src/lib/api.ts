import { config } from './config';
import type {
  AnalyticsOverview,
  AnalyticsRows,
  DocumentDetail,
  DocumentPage,
  DocumentStatus,
  DocumentStatusResponse,
  FileUrlResponse,
  HealthResponse,
  ReviewDetail,
  UploadUrlResponse,
  ValidationResult,
} from './types';

/** Error shape returned by the API (see receipt_shared.http.ErrorResponse). */
export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string | null };
  validation?: ValidationResult;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly validation: ValidationResult | null;

  constructor(
    status: number,
    code: string,
    message: string,
    requestId: string | null = null,
    validation: ValidationResult | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.validation = validation;
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

/** Supplies the current Firebase ID token; `forceRefresh` after a 401. Set by AuthProvider. */
export type TokenProvider = (forceRefresh?: boolean) => Promise<string | null>;
let tokenProvider: TokenProvider = async () => null;

export function setTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider;
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  query?: Record<string, string | number | string[] | null | undefined>;
  auth?: boolean;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === null || value === undefined || value === '') continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, v));
    else params.set(key, String(value));
  }
  const qs = params.toString();
  return `${config.apiBaseUrl}${path}${qs ? `?${qs}` : ''}`;
}

async function send(
  path: string,
  options: RequestOptions,
  token: string | null,
): Promise<Response> {
  const { body, query, headers, auth: _auth, ...rest } = options;
  const finalHeaders = new Headers(headers);
  finalHeaders.set('Accept', 'application/json');
  if (body !== undefined) finalHeaders.set('Content-Type', 'application/json');
  if (token) finalHeaders.set('Authorization', `Bearer ${token}`);
  try {
    return await fetch(buildUrl(path, query), {
      ...rest,
      headers: finalHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'network_error', 'Unable to reach the server. Check your connection.');
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const useAuth = options.auth !== false;
  let response = await send(path, options, useAuth ? await tokenProvider() : null);
  if (response.status === 401 && useAuth) {
    // The ID token may have just expired: refresh once and retry.
    response = await send(path, options, await tokenProvider(true));
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
        data.validation ?? null,
      );
    }
    throw new ApiError(response.status, `http_${response.status}`, response.statusText || 'Error');
  }
  return data as T;
}

export interface DateRange {
  start_date?: string;
  end_date?: string;
}

export const api = {
  health: () => apiRequest<HealthResponse>('/api/v1/health', { auth: false }),

  uploadUrl: (body: {
    filename: string;
    content_type: string;
    size_bytes: number;
    sha256?: string;
  }) => apiRequest<UploadUrlResponse>('/api/v1/documents/upload-url', { method: 'POST', body }),
  documents: (params: { status?: DocumentStatus[]; limit?: number; cursor?: string | null } = {}) =>
    apiRequest<DocumentPage>('/api/v1/documents', {
      query: { status: params.status, limit: params.limit, cursor: params.cursor },
    }),
  document: (id: string) =>
    apiRequest<DocumentDetail>(`/api/v1/documents/${encodeURIComponent(id)}`),
  documentStatus: (id: string) =>
    apiRequest<DocumentStatusResponse>(`/api/v1/documents/${encodeURIComponent(id)}/status`),
  documentFile: (id: string) =>
    apiRequest<FileUrlResponse>(`/api/v1/documents/${encodeURIComponent(id)}/file`),

  reviewQueue: (params: { limit?: number; cursor?: string | null } = {}) =>
    apiRequest<DocumentPage>('/api/v1/review', { query: params }),
  review: (id: string) => apiRequest<ReviewDetail>(`/api/v1/review/${encodeURIComponent(id)}`),
  saveCorrections: (id: string, fields: Record<string, unknown>, acknowledgeDuplicate = false) =>
    apiRequest<ReviewDetail>(`/api/v1/review/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: { fields, acknowledge_duplicate: acknowledgeDuplicate },
    }),
  approve: (id: string) =>
    apiRequest<ReviewDetail>(`/api/v1/review/${encodeURIComponent(id)}/approve`, {
      method: 'POST',
    }),
  reject: (id: string, reason: string) =>
    apiRequest<ReviewDetail>(`/api/v1/review/${encodeURIComponent(id)}/reject`, {
      method: 'POST',
      body: { reason },
    }),

  overview: (range: DateRange) =>
    apiRequest<AnalyticsOverview>('/api/v1/analytics/overview', { query: { ...range } }),
  monthlySpending: (range: DateRange) =>
    apiRequest<AnalyticsRows>('/api/v1/analytics/monthly-spending', { query: { ...range } }),
  categories: (range: DateRange) =>
    apiRequest<AnalyticsRows>('/api/v1/analytics/categories', { query: { ...range } }),
  merchants: (range: DateRange, limit = 10) =>
    apiRequest<AnalyticsRows>('/api/v1/analytics/merchants', { query: { ...range, limit } }),
};
