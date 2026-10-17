import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: './',
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
    rollupOptions: { output: { manualChunks: { react: ['react', 'react-dom'] } } },
  },
  publicDir: 'public',
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
});
