import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// During `npm run dev`, API calls go to the game container (docker compose up).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
});
