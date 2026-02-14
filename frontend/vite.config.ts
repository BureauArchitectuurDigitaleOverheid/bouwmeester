import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';
import path from 'path';
import fs from 'fs';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'prompt',
      includeAssets: ['favicon.ico', 'favicon.svg', 'apple-touch-icon-180x180.png'],
      manifest: {
        name: 'Bouwmeester',
        short_name: 'Bouwmeester',
        description: 'Beleidsportaal voor het Rijk',
        theme_color: '#1E3A5F',
        background_color: '#F8F9FA',
        display: 'standalone',
        lang: 'nl',
        icons: [
          { src: 'pwa-64x64.png', sizes: '64x64', type: 'image/png' },
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'maskable-icon-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
        globIgnores: ['config.js'],
        navigateFallback: 'index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/docs\//],
        runtimeCaching: [
          {
            urlPattern: /^\/api\//,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 },
              networkTimeoutSeconds: 10,
            },
          },
          {
            urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-stylesheets',
              expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
            },
          },
          {
            urlPattern: /^https:\/\/fonts\.gstatic\.com\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-webfonts',
              expiration: { maxEntries: 30, maxAgeSeconds: 60 * 60 * 24 * 365 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: /\/config\.js$/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'config-cache',
              expiration: { maxEntries: 1, maxAgeSeconds: 60 * 5 },
            },
          },
        ],
      },
    }),
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
        if (!fs.existsSync(docsDir)) return;
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
