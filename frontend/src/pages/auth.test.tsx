import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { fakeAuth, renderApp } from '@/test/render';

describe('authentication', () => {
  it('redirects signed-out users to the login page', () => {
    renderApp('/documents', fakeAuth({ user: null }));
    expect(
      screen.getByRole('heading', { name: 'Sign in to Receipt Extractor' }),
    ).toBeInTheDocument();
  });

  it('signs in with email and password', async () => {
    const auth = fakeAuth({ user: null });
    renderApp('/login', auth);
    await userEvent.type(screen.getByLabelText('Email'), 'me@example.test');
    await userEvent.type(screen.getByLabelText('Password'), 'secret-pass');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(auth.signIn).toHaveBeenCalledWith('me@example.test', 'secret-pass');
  });

  it('shows a friendly error for wrong credentials', async () => {
    const auth = fakeAuth({
      user: null,
      signIn: async () => {
        throw Object.assign(new Error('x'), { code: 'auth/invalid-credential' });
      },
    });
    renderApp('/login', auth);
    await userEvent.type(screen.getByLabelText('Email'), 'me@example.test');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.');
  });

  it('validates registration before creating the account', async () => {
    const auth = fakeAuth({ user: null });
    renderApp('/register', auth);
    await userEvent.type(screen.getByLabelText('Email'), 'me@example.test');
    await userEvent.type(screen.getByLabelText('Password'), 'longenough1');
    await userEvent.type(screen.getByLabelText('Confirm password'), 'different1');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Passwords do not match.');
    expect(auth.register).not.toHaveBeenCalled();
  });

  it('signs out from the sidebar', async () => {
    const auth = fakeAuth();
    const { api } = await import('@/lib/api');
    const { vi } = await import('vitest');
    vi.spyOn(api, 'overview').mockReturnValue(new Promise(() => {}));
    vi.spyOn(api, 'documents').mockReturnValue(new Promise(() => {}));
    vi.spyOn(api, 'reviewQueue').mockReturnValue(new Promise(() => {}));
    renderApp('/', auth);
    await userEvent.click(screen.getAllByRole('button', { name: 'Sign out' })[0]!);
    await waitFor(() => expect(auth.signOut).toHaveBeenCalled());
  });
});
