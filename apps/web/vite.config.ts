import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
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
