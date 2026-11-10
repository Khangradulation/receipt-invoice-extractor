import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { authErrorMessage, useAuth } from '@/auth/context';
import { Alert, Button, TextField } from '@/components/ui';

export function AuthShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3">
          <img src="/favicon.svg" alt="" className="size-10" />
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white px-6 py-6 shadow-sm">
          {children}
        </div>
      </div>
    </div>
  );
}

export function LoginPage() {
  const { user, signIn, resetPassword } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={from} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(authErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function onReset() {
    if (!email.trim()) {
      setError('Enter your email address first.');
      return;
    }
    try {
      await resetPassword(email.trim());
      setInfo('If an account exists for this email, a reset link has been sent.');
      setError(null);
    } catch (err) {
      setError(authErrorMessage(err));
    }
  }

  return (
    <AuthShell title="Sign in to Receipt Extractor">
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {error && <Alert tone="error">{error}</Alert>}
        {info && <Alert tone="success">{info}</Alert>}
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" className="w-full" disabled={busy || !email || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </Button>
        <div className="flex justify-between text-sm">
          <button
            type="button"
            onClick={() => void onReset()}
            className="text-indigo-600 hover:text-indigo-500"
          >
            Forgot password?
          </button>
          <Link to="/register" className="font-medium text-indigo-600 hover:text-indigo-500">
            Create account
          </Link>
        </div>
      </form>
    </AuthShell>
  );
}
