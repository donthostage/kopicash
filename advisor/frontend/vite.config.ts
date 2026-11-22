import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const backend = process.env.KOPICASH_BACKEND ?? 'http://127.0.0.1:18747';
// FastAPI compares Origin with the request Host on writes. Keep the browser's Host.
const upstream = { target: backend, changeOrigin: false };
const proxy = { '/api': upstream, '/healthz': upstream, '/static': upstream, '/pocket.webp': upstream };

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 18746, strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: 18745, strictPort: true, proxy },
});
