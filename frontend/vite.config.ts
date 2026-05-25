import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  // Relative asset paths so the build works when loaded from file:// (Electron
  // packaged build) as well as http:// (dev server). Without this, Vite emits
  // /assets/... which resolves to the drive root under file:// and the app
  // boots to a blank window.
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': 'http://127.0.0.1:8765',
      '/files': 'http://127.0.0.1:8765',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    target: 'esnext',
    minify: 'terser',
    terserOptions: {
      compress: {
        passes: 2,
        drop_console: false,
      },
    },
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
          monaco: ['@monaco-editor/react'],
          xterm: ['@xterm/xterm', '@xterm/addon-fit'],
          lucide: ['lucide-react'],
          tanstack: ['@tanstack/react-query'],
          forms: ['react-hook-form', 'zod', 'date-fns'],
          dnd: ['react-dnd', 'react-dnd-html5-backend'],
          motion: ['framer-motion'],
          i18n: ['i18next', 'react-i18next'],
        },
      },
    },
  },
});
