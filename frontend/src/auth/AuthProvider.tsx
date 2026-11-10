import {
  createUserWithEmailAndPassword,
  onIdTokenChanged,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signOut,
  type User,
} from 'firebase/auth';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { setTokenProvider } from '@/lib/api';
import { firebaseAuth } from '@/lib/firebase';
import { AuthContext, type AuthContextValue } from './context';

/** Firebase-backed auth. Tests render <AuthContext.Provider> with a fake value instead. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const auth = firebaseAuth();
    setTokenProvider(async (forceRefresh = false) =>
      auth.currentUser ? auth.currentUser.getIdToken(forceRefresh) : null,
    );
    return onIdTokenChanged(auth, (u) => {
      setFirebaseUser(u);
      setLoading(false);
    });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: firebaseUser ? { uid: firebaseUser.uid, email: firebaseUser.email } : null,
      loading,
      signIn: async (email, password) => {
        await signInWithEmailAndPassword(firebaseAuth(), email, password);
      },
      register: async (email, password) => {
        await createUserWithEmailAndPassword(firebaseAuth(), email, password);
      },
      resetPassword: async (email) => {
        await sendPasswordResetEmail(firebaseAuth(), email);
      },
      signOut: async () => {
        await signOut(firebaseAuth());
        queryClient.clear(); // never show the previous user's data
      },
    }),
    [firebaseUser, loading, queryClient],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
