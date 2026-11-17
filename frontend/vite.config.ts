import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      '/render-api': {
        target: 'https://capstone-project-cmu.onrender.com',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/render-api(?=\/)/, '/api'),
      },
    },
  },
  preview: { host: '127.0.0.1', port: 4173 },
});
