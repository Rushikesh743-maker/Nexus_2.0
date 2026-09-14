import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    allowedHosts: true,
    proxy: {
      // Platform API (FastAPI, see backend/): auth, cases, copilot — all
      // under /api/v1 on the backend, proxied straight through.
      '/api': {
        target: process.env.VITE_CNA_TARGET || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      // Criminal-network-analysis backend (FastAPI, see backend/).
      // Namespaced away from `/api` so it can never collide with the
      // platform REST surface.
      '/cna-api': {
        target: process.env.VITE_CNA_TARGET || 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/cna-api/, '/api'),
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-graph': ['reactflow', 'd3-force'],
          'vendor-charts': ['recharts'],
          'vendor-map': ['leaflet', 'react-leaflet'],
        },
      },
    },
  },
});
