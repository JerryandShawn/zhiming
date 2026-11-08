import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';
import { shellPwaPlugin } from './pwa.plugin';
import { compressedAssetsPlugin } from './compression.plugin';

export default defineConfig({
  plugins: [react(), tailwindcss(), shellPwaPlugin(), compressedAssetsPlugin()],
  base: './',
  build: {
    manifest: true,
    outDir: '../static/dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: fileURLToPath(new URL('./index.html', import.meta.url)),
        legacy: fileURLToPath(new URL('./src/legacy/entry.ts', import.meta.url)),
      },
      output: {
        entryFileNames: (chunk) => (chunk.name === 'legacy' ? 'legacy-stream.js' : 'assets/[name]-[hash].js'),
        manualChunks: {
          react: ['react', 'react-dom'],
          icons: ['lucide-react'],
          // On #/chat the route's tiny chunks queue behind CJK font slices (6 connections per host)
          // and delay the first paragraph; keep them in one chunk.
          'draft-shared': [
            './src/modules/draftApi.ts',
            './src/threads/request.ts',
            './src/chat/sse.ts',
            './src/chat/wireV1.ts',
          ],
        },
      },
    },
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
