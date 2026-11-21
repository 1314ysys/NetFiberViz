import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',                      // 内网静态部署/可嵌入 iframe
  server: {
    proxy: { '/fiber/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } }
  }
})
