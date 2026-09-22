import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import path from 'path';
import fs from 'fs';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'favicon.svg', 'apple-touch-icon-180x180.png', 'logo.png'],
      manifest: {
        name: 'Bouwmeester',
        short_name: 'Bouwmeester',
        description: 'Beleidsportaal voor het Rijk',
        theme_color: '#1E3A5F',
        background_color: '#F8F9FA',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        lang: 'nl',
        icons: [
          { src: 'pwa-64x64.png', sizes: '64x64', type: 'image/png' },
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'maskable-icon-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
        share_target: {
          action: '/share-target',
          method: 'POST',
          enctype: 'multipart/form-data',
          params: {
            title: 'title',
            text: 'text',
            url: 'url',
            files: [
              {
                name: 'images',
                accept: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
              },
            ],
          },
        },
      },
      workbox: {
        importScripts: ['sw-share-target.js'],
        // Take over on the next load instead of waiting for every tab to
        // close. `autoUpdate` only fetches the new worker; without these two
        // it sits in "waiting" while the old one keeps serving its precached
        // bundle, so a deploy reaches nobody who leaves a tab open. Fixes
        // shipped and were reported as still broken because of exactly this.
        skipWaiting: true,
        clientsClaim: true,
        // 5 MB: the main chunk carries mermaid, reactflow and the NLDD design
        // system. Below this the chunk silently drops out of the precache and
        // the app stops working offline.
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
        globIgnores: ['config.js'],
        navigateFallback: 'index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/docs\//],
        runtimeCaching: [
          {
            urlPattern: /^\/api\/(?!auth\/).*/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 },
              networkTimeoutSeconds: 5,
              cacheableResponse: { statuses: [200] },
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
