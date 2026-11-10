import { initializeApp, type FirebaseApp } from 'firebase/app';
import { getAuth, type Auth } from 'firebase/auth';
import { config, firebaseConfigured } from './config';

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

/** Lazily initialised Firebase Auth (only the auth module is used). */
export function firebaseAuth(): Auth {
  if (!firebaseConfigured) {
    throw new Error('Firebase is not configured. Set the VITE_FIREBASE_* variables.');
  }
  if (!auth) {
    app = initializeApp(config.firebase);
    auth = getAuth(app);
  }
  return auth;
}
