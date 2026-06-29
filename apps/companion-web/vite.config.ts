import { sveltekit } from '@sveltejs/kit/vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { svelteTesting } from '@testing-library/svelte/vite';
import { defineConfig } from 'vite';
import path from 'path';

export default defineConfig(({ mode }) => {
  const isTest = mode === 'test';
  return {
    plugins: [
      // During test: bare svelte() with no CSS preprocessor + svelteTesting().
      //   - preprocess:[] prevents the vitePreprocess CSS pipeline from running in jsdom
      //   - svelteTesting() adds the 'browser' export condition so Svelte resolves its
      //     client runtime instead of the SSR server build
      // During build/dev: sveltekit() as normal.
      ...(isTest
        ? [
            svelte({
              hot: false,
              preprocess: [],
            }),
            svelteTesting(),
          ]
        : [sveltekit()]),
    ],
    resolve: {
      alias: {
        // Resolve the local capacitor-audio-session package to its TypeScript source
        // so Vite can tree-shake and bundle it directly (no separate dist/ build step).
        'capacitor-audio-session': path.resolve('../../packages/capacitor-audio-session/src/index.ts'),
      },
    },
    ssr: {
      // @capacitor/core is browser-only; mark it external for the SSR bundle.
      // Capacitor plugins are only invoked client-side, so this is safe.
      external: ['@capacitor/core'],
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.ts'],
      globals: true,
      alias: [
        { find: '$lib/native/plugins', replacement: path.resolve('./src/lib/native/plugins.ts') },
        { find: /^\$lib\/(.*)/, replacement: path.resolve('./src/lib/$1') },
        {
          find: 'companion-core',
          replacement: path.resolve('../../packages/companion-core/src/index.ts'),
        },
        {
          find: 'capacitor-audio-session',
          replacement: path.resolve('../../packages/capacitor-audio-session/src/index.ts'),
        },
        {
          find: '$app/navigation',
          replacement: path.resolve('./src/__mocks__/app-navigation.ts'),
        },
        {
          find: '$app/stores',
          replacement: path.resolve('./src/__mocks__/app-stores.ts'),
        },
        // Mock maplibre-gl and its CSS (WebGL not available in jsdom)
        {
          find: 'maplibre-gl/dist/maplibre-gl.css',
          replacement: path.resolve('./src/__mocks__/maplibre-gl.css.ts'),
        },
        {
          find: 'maplibre-gl',
          replacement: path.resolve('./src/__mocks__/maplibre-gl.ts'),
        },
        // Mock pmtiles in test (no real tile fetching in jsdom)
        {
          find: 'pmtiles',
          replacement: path.resolve('./src/__mocks__/pmtiles.ts'),
        },
      ],
    },
  };
});
