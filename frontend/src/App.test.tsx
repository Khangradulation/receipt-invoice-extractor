import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { renderWithProviders } from './test/render';

const healthy = {
  status: 'ok',
  service: 'api',
  version: '0.1.0',
  environment: 'local',
  timestamp: '2026-01-01T00:00:00Z',
};

describe('App', () => {
  it('shows a healthy API status from the backend', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify(healthy), { status: 200 }));
    renderWithProviders(<App />);

    expect(screen.getByRole('heading', { name: 'System status' })).toBeInTheDocument();
    expect(await screen.findByText('Healthy')).toBeInTheDocument();
    expect(screen.getByText('0.1.0')).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/health', expect.anything());
  });

  it('shows an error when the API is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    renderWithProviders(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('API unreachable');
  });

  it('renders the not-found page for unknown routes', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}'));
    renderWithProviders(<App />, { route: '/nope' });
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });
});
