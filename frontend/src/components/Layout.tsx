import { NavLink, Outlet } from 'react-router-dom';

const NAV_ITEMS = [
  { to: '/', label: 'Brief' },
  { to: '/thesis', label: 'Thesis' },
  { to: '/feed', label: 'Feed' },
];

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <nav className="w-48 shrink-0 border-r border-border bg-surface flex flex-col">
        <div className="px-4 py-5 border-b border-border">
          <h1 className="text-sm font-bold tracking-widest uppercase text-accent">
            Thesis OS
          </h1>
        </div>
        <div className="flex flex-col gap-1 p-2 mt-2">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `px-3 py-2 rounded text-sm transition-colors ${
                  isActive
                    ? 'bg-surface-2 text-accent'
                    : 'text-text-dim hover:text-text hover:bg-surface-2'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </div>
        <div className="mt-auto p-4 text-xs text-text-dim border-t border-border">
          v0.2.0
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
