import { registerPlugin } from "@capacitor/core";

type FcmBridgePlugin = {
  getFcmToken(): Promise<{ token: string }>;
  registerPushDevice(options: {
    apiBase: string;
    accessToken: string;
    token: string;
    platform: string;
    deviceId?: string | null;
    appVersion?: string | null;
  }): Promise<{ status: number; body: string }>;
};

export const FcmBridge = registerPlugin<FcmBridgePlugin>("FcmBridge");
