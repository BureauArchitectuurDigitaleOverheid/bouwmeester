import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';
import fs from 'fs';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'serve-root-docs',
      configureServer(server) {
        const docsDir = path.resolve(__dirname, '../docs');
        server.middlewares.use('/docs', (req, res, next) => {
          import('sirv').then((m) =>
            m.default(docsDir, { dev: true, etag: true })(req, res, next),
          ).catch(next);
        });
      },
    },
    {
      name: 'copy-root-docs',
      closeBundle() {
        const docsDir = path.resolve(__dirname, '../docs');
        const outDir = path.resolve(__dirname, 'dist/docs');
        fs.mkdirSync(outDir, { recursive: true });
        for (const file of fs.readdirSync(docsDir)) {
          fs.copyFileSync(path.join(docsDir, file), path.join(outDir, file));
        }
      },
    },
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
