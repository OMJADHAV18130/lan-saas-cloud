import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The dev server binds to 0.0.0.0 so other lab machines can open the UI at
// http://<server-lan-ip>:5173  (see docs/lan-deployment.md).
// The /api proxy target is configurable so remote clients never hardcode
// "localhost" as the backend address.
const proxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: true,
    port: 4173,
    proxy: {
      '/api': { target: proxyTarget, changeOrigin: true },
    },
  },
});
