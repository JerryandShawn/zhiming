import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
process.env.TZ = 'Asia/Shanghai';
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/*.test.{ts,tsx}'],
    maxWorkers: 2,
    env: { TZ: 'Asia/Shanghai' },
  },
});
