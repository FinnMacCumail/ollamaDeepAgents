// https://nuxt.com/docs/api/configuration/nuxt-config
//
// Ports (defined ONCE here for the frontend side; the backend side is WEB_PORT in
// src/web/config.py): backend 8010, frontend 3010. 8000 is NetBox, 8001/8002 the
// claude-agentic-sdk app, 58123 llama-server, 11434 Ollama.
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },

  modules: [
    '@nuxtjs/tailwindcss'
  ],

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    public: {
      wsUrl: process.env.NUXT_PUBLIC_WS_URL || 'ws://localhost:8010/ws/chat',
      apiUrl: process.env.NUXT_PUBLIC_API_URL || 'http://localhost:8010'
    }
  },

  typescript: {
    strict: true,
    typeCheck: false  // vue-tsc left off, as in the claude-agentic-sdk frontend
  },

  // The browser talks straight to FastAPI (no Nitro proxy), so this flag is not
  // strictly needed; kept for parity with the source app.
  nitro: {
    experimental: {
      websocket: true
    }
  },

  app: {
    head: {
      title: 'RTF research — NetBox Web Chat',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'RTF research: local-LLM chat over NetBox infrastructure data' }
      ],
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/logo.svg' }
      ]
    }
  },

  devServer: {
    port: 3010
  },

  imports: {
    dirs: ['types', 'utils']
  }
})
