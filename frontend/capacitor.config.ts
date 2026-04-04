import type { CapacitorConfig } from "@capacitor/cli";

const isDev = process.env.CAPACITOR_ENV === "dev";

const config: CapacitorConfig = {
  appId: "app.praina.mobile",
  appName: "Praina",
  webDir: "dist",
  server: {
    androidScheme: "https",
    ...(isDev
      ? { url: "http://localhost:5173", cleartext: true }
      : { url: "https://c3lab.poliba.it/praina" }),
  },
  ios: {
    contentInset: "automatic",
  },
};

export default config;
