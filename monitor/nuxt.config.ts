// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  future: {
    compatibilityVersion: 4,
  },

  css: ['~/assets/css/main.css'],

  modules: [
    '@nuxtjs/tailwindcss',
    '@pinia/nuxt',
    '@vueuse/nuxt',
  ],

  typescript: {
    strict: true,
    typeCheck: false, // Disable for faster dev builds
  },

  app: {
    head: {
      title: 'Trident Monitor',
      meta: [
        { name: 'description', content: 'Local development UI for Trident workflow visualization' },
      ],
    },
  },

  // Server configuration for API routes
  nitro: {
    experimental: {
      websocket: true,
    },
  },

  // Enable auto-imports for components in app directory
  components: {
    dirs: [
      {
        path: '~/components',
        pathPrefix: false,
      },
      {
        path: '~/components/ui',
        pathPrefix: false,
      },
    ],
  },

  // Auto-import stores
  imports: {
    dirs: ['stores'],
  },

  // Runtime configuration
  runtimeConfig: {
    // Server-side only
    projectPath: process.env.TRIDENT_PROJECT_PATH || '',
    // Public (client-side available)
    public: {
      appName: 'Trident Monitor',
    },
  },

  // Vite optimization - pre-bundle heavy dependencies at startup
  vite: {
    optimizeDeps: {
      include: [
        '@vue-flow/core',
        '@vue-flow/background',
        '@vue-flow/controls',
        '@vue-flow/minimap',
        'd3-selection',
        'd3-zoom',
        'd3-drag',
        'lucide-vue-next',
      ],
    },
    // SSR optimization - externalize large packages to avoid re-bundling
    ssr: {
      noExternal: ['@vue-flow/core', '@vue-flow/background', '@vue-flow/controls', '@vue-flow/minimap'],
    },
  },
})
