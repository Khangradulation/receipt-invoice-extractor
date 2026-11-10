import { describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest, setTokenProvider } from './api';

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

describe('apiRequest', () => {
  it('sends the Firebase ID token', async () => {
    setTokenProvider(async () => 'tok-1');
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({ ok: 1 }));
    await expect(apiRequest('/x')).resolves.toEqual({ ok: 1 });
    expect(new Headers(spy.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe('Bearer tok-1');
  });

  it('refreshes the token once after a 401 and retries', async () => {
    const provider = vi.fn(async (force?: boolean) => (force ? 'fresh' : 'stale'));
    setTokenProvider(provider);
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockResolvedValueOnce(ok({ ok: 2 }));
    await expect(apiRequest('/x')).resolves.toEqual({ ok: 2 });
    expect(provider).toHaveBeenLastCalledWith(true);
    expect(new Headers(spy.mock.calls[1]?.[1]?.headers).get('Authorization')).toBe('Bearer fresh');
  });

  it('skips auth for public endpoints', async () => {
    setTokenProvider(async () => 'tok');
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({}));
    await apiRequest('/health', { auth: false });
    expect(new Headers(spy.mock.calls[0]?.[1]?.headers).get('Authorization')).toBeNull();
  });

  it('builds query strings, repeating array params and dropping empty ones', async () => {
    setTokenProvider(async () => null);
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({}));
    await apiRequest('/docs', { query: { status: ['VALID', 'FAILED'], limit: 5, cursor: null } });
    expect(spy.mock.calls[0]?.[0]).toBe('/docs?status=VALID&status=FAILED&limit=5');
  });

  it('maps API errors, including validation details', async () => {
    setTokenProvider(async () => null);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: 'conflict',
            message: 'Fix the remaining validation errors.',
            request_id: 'r1',
          },
          validation: { is_valid: false },
        }),
        { status: 409 },
      ),
    );
    const err = await apiRequest('/x').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 409,
      code: 'conflict',
      requestId: 'r1',
      validation: { is_valid: false },
    });
  });

  it('maps network failures', async () => {
    setTokenProvider(async () => null);
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(apiRequest('/x')).rejects.toMatchObject({ code: 'network_error', status: 0 });
  });
});
