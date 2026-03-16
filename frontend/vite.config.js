import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(function (_a) {
    var mode = _a.mode;
    var env = loadEnv(mode, ".", "");
    var portValue = env.VITE_DEV_PORT;
    if (!portValue) {
        throw new Error("VITE_DEV_PORT must be set in frontend .env.");
    }
    return {
        plugins: [react()],
        server: {
            port: Number(portValue),
            strictPort: true,
        },
    };
});
