import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const portValue = env.VITE_DEV_PORT;
  const publicBase = env.VITE_PUBLIC_BASE || "/";

  if (!portValue) {
    throw new Error("VITE_DEV_PORT must be set in frontend .env.");
  }

  return {
    plugins: [react()],
    base: publicBase,
    server: {
      port: Number(portValue),
      strictPort: true,
    },
  };
});
