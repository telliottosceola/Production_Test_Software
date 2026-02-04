import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	// Tauri expects a fixed port
	server: {
		port: 5173,
		strictPort: true
	},
	// Build settings for Tauri
	build: {
		target: 'esnext'
	}
});
