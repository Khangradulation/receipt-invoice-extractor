import { describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest } from './api';

function mockFetch(response: Response | Error) {
  return vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(() =>
      response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
    );
}

describe('apiRequest', () => {
  it('returns parsed JSON on success', async () => {
    mockFetch(new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    await expect(apiRequest('/x')).resolves.toEqual({ ok: 1 });
  });

  it('sends bearer token and JSON body', async () => {
    const spy = mockFetch(new Response('{}', { status: 200 }));
    await apiRequest('/x', { method: 'POST', body: { a: 1 }, token: 't0k' });
    const init = spy.mock.calls[0]?.[1];
    const headers = new Headers(init?.headers);
    expect(headers.get('Authorization')).toBe('Bearer t0k');
    expect(headers.get('Content-Type')).toBe('application/json');
    expect(init?.body).toBe('{"a":1}');
  });

  it('maps API error bodies to ApiError', async () => {
    mockFetch(
      new Response(
        JSON.stringify({ error: { code: 'not_found', message: 'Nope', request_id: 'r1' } }),
        { status: 404 },
      ),
    );
    const err = await apiRequest('/x').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: 'not_found', message: 'Nope', requestId: 'r1' });
  });

  it('maps network failures to a network_error', async () => {
    mockFetch(new TypeError('Failed to fetch'));
    await expect(apiRequest('/x')).rejects.toMatchObject({ code: 'network_error', status: 0 });
  });
});
