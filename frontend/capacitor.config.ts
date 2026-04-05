import type { CapacitorConfig } from "@capacitor/cli";

const isDev = process.env.CAPACITOR_ENV === "dev";

const config: CapacitorConfig = {
  appId: "app.praina.mobile",
  appName: "Praina",
  webDir: "dist",
  server: {
    androidScheme: "https",
    ...(isDev && { url: "http://localhost:5173", cleartext: true }),
  },
  plugins: {
    SplashScreen: {
      launchAutoHide: true,
      launchShowDuration: 1500,
      backgroundColor: "#111113",
      androidSplashResourceName: "splash",
      showSpinner: false,
      launchFadeOutDuration: 300,
    },
    Keyboard: {
      resize: "body",
      resizeOnFullScreen: true,
    },
  },
  android: {
    backgroundColor: "#111113",
    overScrollMode: "never" as unknown as string,
  },
  ios: {
    contentInset: "automatic",
    backgroundColor: "#111113",
  },
};

export default config;
