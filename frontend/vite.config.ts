import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { viteStaticCopy } from 'vite-plugin-static-copy'

// USWDS ships fonts/images we must serve; the Sass entry (src/styles/styles.scss)
// points $theme-font-path/$theme-image-path at /fonts and /img.
const USWDS = 'node_modules/@uswds/uswds'

export default defineConfig({
  plugins: [
    react(),
    viteStaticCopy({
      targets: [
        { src: `${USWDS}/dist/img`, dest: '.' },
        { src: `${USWDS}/dist/fonts`, dest: '.' },
      ],
    }),
  ],
  css: {
    preprocessorOptions: {
      scss: {
        // USWDS 3 requires the /packages directory on the Sass load path.
        loadPaths: [`${USWDS}/packages`],
        quietDeps: true,
        silenceDeprecations: ['mixed-decls', 'global-builtin', 'import'],
      },
    },
  },
  server: {
    port: 5173,
    // Same-origin proxy to the FastAPI backend (docs/ui-design.md §3): the browser
    // sees one origin, so the BFF session cookie (§11) works without CORS.
    proxy: {
      '/v1': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
