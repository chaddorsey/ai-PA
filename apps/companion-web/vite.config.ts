import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import path from 'path';

export default defineConfig({
  plugins: [sveltekit()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    globals: true,
    alias: [
      { find: '$lib/native/plugins', replacement: path.resolve('./src/lib/native/plugins.ts') },
      { find: /^\$lib\/(.*)/, replacement: path.resolve('./src/lib/$1') },
      {
        find: 'companion-core',
        replacement: '/Volumes/main-drive/ai-PA/packages/companion-core/src/index.ts',
      },
    ],
  },
});
