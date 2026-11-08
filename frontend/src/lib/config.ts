/** Runtime configuration, read once from Vite's build-time environment. */
export const config = {
  /** Base URL of the API. Empty string = same origin (dev proxy or reverse proxy). */
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, ''),
} as const;
