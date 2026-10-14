import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Backend base URL comes from VITE_API_BASE_URL at build/dev time.
// No server secrets are ever exposed through VITE_ variables.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // Split heavy vendor libraries so the app chunk stays small.
          charts: ['recharts'],
          router: ['react-router-dom'],
          icons: ['lucide-react'],
        },
      },
    },
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    css: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
});
