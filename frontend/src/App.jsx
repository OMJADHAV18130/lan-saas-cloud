import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import Layout from './components/Layout';
import Admin from './pages/Admin';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import MyFiles from './pages/MyFiles';
import Profile from './pages/Profile';
import Register from './pages/Register';
import UploadFile from './pages/UploadFile';

function FullPageSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <div className="flex items-center gap-3 text-slate-500">
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600" />
        Loading…
      </div>
    </div>
  );
}

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <FullPageSpinner />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function RequireAdmin({ children }) {
  const { user, loading, isAdmin } = useAuth();
  if (loading) return <FullPageSpinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (!isAdmin) return <Navigate to="/dashboard" replace />;
  return children;
}

function PublicOnly({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <FullPageSpinner />;
  if (user) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
        <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />

        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/files" element={<MyFiles />} />
          <Route path="/upload" element={<UploadFile />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/admin" element={<RequireAdmin><Admin /></RequireAdmin>} />
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  );
}
