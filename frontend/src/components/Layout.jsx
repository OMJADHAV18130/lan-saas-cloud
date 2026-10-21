import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import StorageStatusBadge from './StorageStatusBadge';

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: 'M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z' },
  { to: '/files', label: 'My Files', icon: 'M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z' },
  { to: '/upload', label: 'Upload File', icon: 'M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5' },
  { to: '/profile', label: 'Profile', icon: 'M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z' },
];

function Icon({ d, className = 'h-5 w-5' }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}

export default function Layout() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const nav = (
    <nav className="flex-1 space-y-1 px-3">
      {navItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          onClick={() => setSidebarOpen(false)}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              isActive
                ? 'bg-brand-50 text-brand-700'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`
          }
        >
          <Icon d={item.icon} />
          {item.label}
        </NavLink>
      ))}
      {isAdmin && (
        <NavLink
          to="/admin"
          onClick={() => setSidebarOpen(false)}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              isActive
                ? 'bg-brand-50 text-brand-700'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`
          }
        >
          <Icon d="M10.343 3.94c.09-.542.56-.94 1.11-.94h1.093c.55 0 1.02.398 1.11.94l.149.894c.07.424.384.764.78.93.398.164.855.142 1.205-.108l.737-.527a1.125 1.125 0 011.45.12l.773.774c.39.389.44 1.002.12 1.45l-.527.737c-.25.35-.272.806-.107 1.204.165.397.505.71.93.78l.893.15c.543.09.94.56.94 1.109v1.094c0 .55-.397 1.02-.94 1.11l-.894.149c-.424.07-.764.383-.929.78-.165.398-.143.854.107 1.204l.527.738c.32.447.269 1.06-.12 1.45l-.774.773a1.125 1.125 0 01-1.449.12l-.738-.527c-.35-.25-.806-.272-1.203-.107-.398.165-.71.505-.781.929l-.149.894c-.09.542-.56.94-1.11.94h-1.094c-.55 0-1.019-.398-1.11-.94l-.148-.894c-.071-.424-.384-.764-.781-.93-.398-.164-.854-.142-1.204.108l-.738.527c-.447.32-1.06.269-1.45-.12l-.773-.774a1.125 1.125 0 01-.12-1.45l.527-.737c.25-.35.272-.806.108-1.204-.165-.397-.506-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.094c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.765-.383.93-.78.165-.398.143-.854-.108-1.204l-.526-.738a1.125 1.125 0 01.12-1.45l.773-.773a1.125 1.125 0 011.45-.12l.737.527c.35.25.807.272 1.204.107.397-.165.71-.505.78-.929l.15-.894z M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          Admin Dashboard
        </NavLink>
      )}
    </nav>
  );

  const brand = (
    <div className="flex items-center gap-2 px-5 py-5">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
        CS
      </div>
      <div>
        <p className="text-sm font-semibold text-slate-900">LAN Cloud Storage</p>
        <p className="text-xs text-slate-500">HDFS-powered SaaS</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Sidebar (desktop) */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-200 bg-white lg:flex">
        {brand}
        {nav}
        <div className="mt-auto">
          <StorageStatusBadge />
        </div>
      </aside>

      {/* Sidebar (mobile) */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setSidebarOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-white shadow-xl">
            {brand}
            {nav}
            <div className="mt-auto">
              <StorageStatusBadge />
            </div>
          </aside>
        </div>
      )}

      <div className="lg:pl-64">
        {/* Topbar */}
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-6">
          <button type="button" className="btn-secondary !px-2 lg:hidden"
            onClick={() => setSidebarOpen(true)} aria-label="Open menu">
            <Icon d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" className="h-5 w-5" />
          </button>
          <div className="hidden text-sm text-slate-500 sm:block">
            Private cloud file service for the laboratory LAN
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm font-medium text-slate-800">{user?.username}</p>
              <p className="text-xs text-slate-500">{isAdmin ? 'Administrator' : 'User'}</p>
            </div>
            <button type="button" onClick={handleLogout} className="btn-secondary !py-1.5">
              Sign out
            </button>
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
