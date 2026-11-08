import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="py-24 text-center">
      <p className="text-sm font-semibold text-indigo-600">404</p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Page not found</h1>
      <p className="mt-2 text-sm text-slate-500">The page you are looking for does not exist.</p>
      <Link
        to="/"
        className="mt-6 inline-block text-sm font-medium text-indigo-600 hover:text-indigo-500"
      >
        Go home
      </Link>
    </div>
  );
}
