import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/cn';
import { navItems } from './navigation';

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col bg-slate-900 text-slate-300">
      <div className="flex h-16 items-center gap-2.5 px-5">
        <img src="/favicon.svg" alt="" className="size-8" />
        <span className="text-sm font-semibold tracking-tight text-white">Receipt Extractor</span>
      </div>
      <nav aria-label="Main" className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive ? 'bg-slate-800 text-white' : 'hover:bg-slate-800/60 hover:text-white',
              )
            }
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.75}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="size-5 shrink-0"
              aria-hidden="true"
            >
              <path d={item.icon} />
            </svg>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <p className="px-5 py-4 text-xs text-slate-500">v0.1.0</p>
    </div>
  );
}
