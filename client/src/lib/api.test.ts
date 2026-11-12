import { describe, it, expect, vi } from 'vitest';
import { ApiClient, ApiError } from './api';
import type { TokenPair } from './types';

function pair(label = 'a', exp = Date.now() / 1000 + 600): TokenPair {
  const payload = btoa(JSON.stringify({ sub: 'member:42', role: 'member', exp })).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  return { access_token: `header.${payload}.${label}`, refresh_token: `refresh-${label}`, token_type: 'bearer', expires_in: 600 };
}
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const storage = () => {
  const data = new Map<string, string>();
  return { getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => { data.set(key, value); }, removeItem: (key: string) => { data.delete(key); }, clear: () => data.clear(), key: () => null, get length() { return data.size; } } satisfies Storage;
};

describe('API client', () => {
  it('sends the OAuth form to the correct login endpoint and restores the tab session', async () => {
    const tokens = pair(); const local = storage();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json(tokens));
    const api = new ApiClient(fetcher, local);
    await api.login('member', 'ana@example.com', 'password123');
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe('/auth/login');
    expect(init?.body?.toString()).toBe('username=ana%40example.com&password=password123');
    expect(new ApiClient(fetcher, local).getSession()?.identity.subject).toBe('member:42');
    expect(local.getItem('gymflow.session')).not.toContain('password123');
    api.logout(); expect(local.length).toBe(0);
  });

  it('uses the employee login endpoint', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json(pair()));
    await new ApiClient(fetcher, storage()).login('employee', 'staff@example.com', 'password123');
    expect(fetcher.mock.calls[0][0]).toBe('/auth/employees/login');
  });

  it('shares one refresh across simultaneous expired-token requests', async () => {
    const fresh = pair('b'); let refreshCount = 0;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url, init) => {
      if (String(url).endsWith('/login')) return json(pair('a', 0));
      if (url === '/auth/refresh') {
        refreshCount += 1;
        expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer refresh-a');
        await new Promise((resolve) => setTimeout(resolve, 5));
        return json(fresh);
      }
      expect(new Headers(init?.headers).get('Authorization')).toBe(`Bearer ${fresh.access_token}`);
      return json({ ok: true });
    });
    const api = new ApiClient(fetcher, storage());
    await api.login('member', 'ana@example.com', 'password123');
    await Promise.all([api.request('/api/one'), api.request('/api/two')]);
    expect(refreshCount).toBe(1);
    expect(api.getSession()?.tokens.refresh_token).toBe('refresh-b');
  });

  it('retries a 401 with rotated credentials only once', async () => {
    const tokens = pair('a'); const rotated = pair('b'); let requests = 0;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => {
      if (String(url).endsWith('/login')) return json(tokens);
      if (url === '/auth/refresh') return json(rotated);
      requests += 1;
      return requests === 1 ? json({ detail: 'Access token expired' }, 401) : json({ ok: true });
    });
    const api = new ApiClient(fetcher, storage());
    await api.login('member', 'ana@example.com', 'password123');
    await expect(api.request('/api/test')).resolves.toEqual({ ok: true });
    expect(requests).toBe(2);
  });

  it('clears the session if the refresh is expired', async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => String(url).endsWith('/login') ? json(pair('a', 0)) : json({ detail: 'Refresh token expired' }, 401));
    const api = new ApiClient(fetcher, storage());
    await api.login('member', 'ana@example.com', 'password123');
    await expect(api.request('/api/test')).rejects.toMatchObject({ status: 401 });
    expect(api.getSession()).toBeNull();
  });

  it('does not resurrect a session after logout during refresh', async () => {
    let release: (value: Response) => void = () => {};
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => {
      if (String(url).endsWith('/login')) return json(pair('a', 0));
      return new Promise<Response>((resolve) => { release = resolve; });
    });
    const api = new ApiClient(fetcher, storage());
    await api.login('member', 'ana@example.com', 'password123');
    const pending = api.request('/api/test');
    api.logout(); release(json(pair('b')));
    await expect(pending).rejects.toBeInstanceOf(ApiError);
    expect(api.getSession()).toBeNull();
  });

  it('does not replay mutations on conflicts or server errors', async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => String(url).endsWith('/login') ? json(pair()) : json({ detail: 'Member has already checked in today' }, 409));
    const api = new ApiClient(fetcher, storage());
    await api.login('member', 'ana@example.com', 'password123');
    await expect(api.generatePass()).rejects.toThrow('Tu entrada de hoy ya fue registrada');
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('preserves exact price strings and PATCH omission semantics', async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => String(url).endsWith('/login') ? json(pair()) : json({ ok: true }));
    const api = new ApiClient(fetcher, storage());
    await api.login('employee', 'admin@example.com', 'password123');
    await api.patchPlan(7, { price: '450.25' });
    const [, init] = fetcher.mock.calls[1];
    expect(init?.method).toBe('PATCH');
    expect(init?.body).toBe('{"price":"450.25"}');
  });

  it('handles blocked storage without breaking the login screen', () => {
    const blocked = { getItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } } as unknown as Storage;
    expect(new ApiClient(vi.fn(), blocked).getSession()).toBeNull();
  });

  it('registers members publicly without sending staff credentials', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json({ member_id: 1 }));
    const api = new ApiClient(fetcher, storage());
    await api.registerMember({ name: 'Ana', email: 'ana@example.com', password: 'password123' });
    expect(fetcher.mock.calls[0][0]).toBe('/auth/register');
    expect(new Headers(fetcher.mock.calls[0][1]?.headers).has('Authorization')).toBe(false);
  });
});
