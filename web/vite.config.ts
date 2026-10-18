import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: './',
  build: {
    manifest: true,
    outDir: '../static/dist',
    emptyOutDir: true,
    rollupOptions: { output: { manualChunks: { react: ['react', 'react-dom'] } } },
  },
  publicDir: 'public',
  server: {
    watch: { ignored: ['**/test-results/**', '**/evidence/**'] },
    proxy: {
      '/api': 'http://127.0.0.1:8002',
      '/static': 'http://127.0.0.1:8002',
      '/__test__': 'http://127.0.0.1:8002',
    },
  },
  preview: {
    proxy: {
      '/api': 'http://127.0.0.1:8002',
      '/static': 'http://127.0.0.1:8002',
      '/__test__': 'http://127.0.0.1:8002',
    },
  },
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
});
