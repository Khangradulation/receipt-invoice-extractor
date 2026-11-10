import { LogOut } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '@/auth/context';
import { cn } from '@/lib/cn';
import { navItems } from './navigation';

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user, signOut } = useAuth();
  return (
    <div className="flex h-full flex-col bg-slate-900 text-slate-300">
      <div className="flex h-16 items-center gap-2.5 px-5">
        <img src="/favicon.svg" alt="" className="size-8" />
        <span className="text-sm font-semibold tracking-tight text-white">Receipt Extractor</span>
      </div>
      <nav aria-label="Main" className="flex-1 space-y-1 px-3 py-4">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive ? 'bg-slate-800 text-white' : 'hover:bg-slate-800/60 hover:text-white',
              )
            }
          >
            <Icon className="size-5 shrink-0" aria-hidden="true" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-slate-800 px-3 py-4">
        <p className="truncate px-3 text-xs text-slate-400" title={user?.email ?? ''}>
          {user?.email}
        </p>
        <button
          type="button"
          onClick={() => void signOut()}
          className="mt-2 flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-slate-800/60 hover:text-white"
        >
          <LogOut className="size-5" aria-hidden="true" />
          Sign out
        </button>
      </div>
    </div>
  );
}
