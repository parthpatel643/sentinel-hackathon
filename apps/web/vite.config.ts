import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'Sentinel Field',
        short_name: 'Sentinel',
        description: 'Sentinel Platform — Field PWA for officers on the ground',
        theme_color: '#12141b',
        background_color: '#12141b',
        display: 'standalone',
        start_url: '/field',
        scope: '/',
        icons: [
          { src: '/pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/pwa-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // The Operator Console's own API calls (cameras, detections, live
        // video) must never be served from a stale cache — only the Field
        // PWA's own app shell (JS/CSS/HTML) is precached. The Field UI
        // itself decides what to do when a fetch fails offline (its own
        // IndexedDB outbox, not a service-worker cache lie).
        navigateFallback: '/field',
        globPatterns: ['**/*.{js,css,html,svg,png,ttf}'],
        // The single app bundle now carries three languages' worth of
        // strings (i18next resources) plus maplibre/hls.js/radix — past
        // workbox's 2 MiB default precache ceiling. Raised, not split,
        // because the Field PWA's whole point is a working offline app
        // shell: a chunk left out of the precache list is a chunk the
        // officer's phone won't have when it matters.
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
      },
      devOptions: {
        // Lets the Field PWA be tested (install prompt, offline shell)
        // against the Vite dev server, not only a production build.
        enabled: true,
      },
    }),
  ],
  server: {
    port: 5173,
  },
  // maplibre-gl loads its tile-decoding work via an internal Web Worker
  // chunk (maplibre-gl-worker.mjs); Vite's esbuild-based dep optimizer
  // doesn't resolve that dynamic import correctly when the package is
  // pre-bundled, which silently breaks all tile rendering. Excluding it
  // from optimizeDeps lets the browser load the package's native ESM as-is.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
})
