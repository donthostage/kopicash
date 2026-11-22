import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const backend = process.env.KOPICASH_BACKEND ?? 'http://127.0.0.1:18745';
const proxy = { '/api': backend, '/healthz': backend, '/static': backend, '/pocket.webp': backend };

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 18746, strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: 18746, strictPort: true, proxy },
});
