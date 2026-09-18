/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // При разработке фронт живёт на 5173, а сервис на 8000.
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: { outDir: 'dist' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setup.ts',
  },
});
