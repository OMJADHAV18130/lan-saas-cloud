import axios from 'axios';

// API base resolution:
//  - VITE_API_BASE_URL set  -> absolute controller URL (split LAN deployment)
//  - otherwise              -> same origin ("/api"), which works when the
//                              controller serves the built frontend and when
//                              the Vite dev proxy is in front of FastAPI.
const BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

const TOKEN_KEY = 'lansaas_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

const api = axios.create({ baseURL: BASE, timeout: 60000 });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Normalise every backend error to { code, message, details }.
function normalise(error) {
  const payload = error?.response?.data?.error;
  if (payload?.message) {
    return { status: error.response.status, ...payload };
  }
  if (error?.code === 'ECONNABORTED') {
    return { status: 0, code: 'timeout', message: 'The server took too long to respond.' };
  }
  if (!error?.response) {
    return {
      status: 0,
      code: 'network_error',
      message: 'Cannot reach the Cloud Controller. Check that it is running '
        + 'and that the API address is correct.',
    };
  }
  return { status: error.response.status, code: 'error', message: 'Unexpected server response.' };
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const normalised = normalise(error);
    error.normalised = normalised;
    if (error.response?.status === 401 && getToken()) {
      // Token expired or revoked: drop it so the router sends the user home.
      setToken(null);
      if (window.location.pathname !== '/login') {
        window.location.assign('/login');
      }
    }
    return Promise.reject(error);
  }
);

export function errorOf(error) {
  return error?.normalised || { status: 0, code: 'error', message: 'Something went wrong.' };
}

// --- auth -----------------------------------------------------------------
export const authApi = {
  register: (username, password) => api.post('/auth/register', { username, password }),
  login: (username, password) => api.post('/auth/login', { username, password }),
  me: () => api.get('/auth/me'),
};

// --- files ----------------------------------------------------------------
export const filesApi = {
  list: (params) => api.get('/files', { params }),
  upload: (formData, onProgress) =>
    api.post('/files/upload', formData, {
      timeout: 0,
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded * 100) / event.total));
        }
      },
    }),
  remove: (fileId) => api.delete(`/files/${fileId}`),
  // Streams the file with the auth header, then triggers a browser download.
  download: async (fileId, originalName) => {
    const response = await api.get(`/files/${fileId}/download`, {
      responseType: 'blob',
      timeout: 0,
    });
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = originalName || 'download';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    return response.data;
  },
};

// --- dashboard / profile / admin ------------------------------------------
export const dashboardApi = { stats: () => api.get('/dashboard/stats') };
export const healthApi = {
  health: () => api.get('/health'),
  storageStatus: () => api.get('/storage/status'),
};
export const adminApi = {
  stats: () => api.get('/admin/stats'),
  users: () => api.get('/admin/users'),
  hdfsStatus: () => api.get('/admin/hdfs-status'),
  audit: (params) => api.get('/admin/audit', { params }),
  setRole: (userId, role) => api.patch(`/admin/users/${userId}/role`, { role }),
};

export default api;
