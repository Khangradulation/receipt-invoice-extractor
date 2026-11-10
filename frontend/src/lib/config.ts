/** Runtime configuration, read once from Vite's build-time environment (all values are public). */
export const config = {
  /** Base URL of the API. Empty string = same origin (dev proxy or reverse proxy). */
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, ''),
  firebase: {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY ?? '',
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN ?? '',
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID ?? '',
    appId: import.meta.env.VITE_FIREBASE_APP_ID ?? '',
  },
  maxUploadBytes: 15 * 1024 * 1024,
} as const;

export const firebaseConfigured = Boolean(config.firebase.apiKey && config.firebase.projectId);
