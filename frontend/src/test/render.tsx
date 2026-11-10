import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { App } from '@/App';
import { AuthContext, type AuthContextValue } from '@/auth/context';

export function fakeAuth(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    user: { uid: 'user_A', email: 'a@example.test' },
    loading: false,
    signIn: vi.fn(async () => {}),
    register: vi.fn(async () => {}),
    resetPassword: vi.fn(async () => {}),
    signOut: vi.fn(async () => {}),
    ...overrides,
  };
}

/** Render the whole app at `route` with a fake auth context and isolated query cache. */
export function renderApp(route = '/', auth: AuthContextValue = fakeAuth()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    auth,
    ...render(
      <QueryClientProvider client={client}>
        <AuthContext.Provider value={auth}>
          <MemoryRouter initialEntries={[route]}>
            <App />
          </MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>,
    ),
  };
}
