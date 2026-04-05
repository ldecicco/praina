package app.praina.mobile;

import androidx.annotation.NonNull;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.firebase.messaging.FirebaseMessaging;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.DataOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

@CapacitorPlugin(name = "FcmBridge")
public class FcmBridgePlugin extends Plugin {
    @PluginMethod
    public void getFcmToken(final PluginCall call) {
        FirebaseMessaging.getInstance().getToken().addOnCompleteListener(task -> {
            if (!task.isSuccessful()) {
                Exception exception = task.getException();
                call.reject(exception != null ? exception.getMessage() : "Failed to fetch FCM token.");
                return;
            }

            String token = task.getResult();
            if (token == null || token.trim().isEmpty()) {
                call.reject("FCM token is empty.");
                return;
            }

            JSObject result = new JSObject();
            result.put("token", token);
            call.resolve(result);
        });
    }

    @PluginMethod
    public void registerPushDevice(final PluginCall call) {
        final String apiBase = call.getString("apiBase");
        final String accessToken = call.getString("accessToken");
        final String token = call.getString("token");
        final String platform = call.getString("platform");
        final String deviceId = call.getString("deviceId");
        final String appVersion = call.getString("appVersion");

        if (apiBase == null || apiBase.trim().isEmpty()) {
            call.reject("apiBase is required.");
            return;
        }
        if (accessToken == null || accessToken.trim().isEmpty()) {
            call.reject("accessToken is required.");
            return;
        }
        if (token == null || token.trim().isEmpty()) {
            call.reject("token is required.");
            return;
        }
        if (platform == null || platform.trim().isEmpty()) {
            call.reject("platform is required.");
            return;
        }

        getBridge().execute(() -> {
            HttpURLConnection connection = null;
            try {
                String normalizedBase = apiBase.endsWith("/") ? apiBase.substring(0, apiBase.length() - 1) : apiBase;
                URL url = new URL(normalizedBase + "/auth/me/push-device");

                JSONObject payload = new JSONObject();
                payload.put("token", token);
                payload.put("platform", platform);
                payload.put("device_id", deviceId == null ? JSONObject.NULL : deviceId);
                payload.put("app_version", appVersion == null ? JSONObject.NULL : appVersion);
                byte[] bodyBytes = payload.toString().getBytes(StandardCharsets.UTF_8);

                connection = (HttpURLConnection) url.openConnection();
                connection.setRequestMethod("POST");
                connection.setConnectTimeout(10000);
                connection.setReadTimeout(10000);
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", "application/json");
                connection.setRequestProperty("Authorization", "Bearer " + accessToken);

                try (OutputStream outputStream = connection.getOutputStream();
                     DataOutputStream writer = new DataOutputStream(outputStream)) {
                    writer.write(bodyBytes);
                    writer.flush();
                }

                int statusCode = connection.getResponseCode();
                String responseBody = readResponseBody(statusCode >= 200 && statusCode < 300
                    ? connection.getInputStream()
                    : connection.getErrorStream());

                if (statusCode < 200 || statusCode >= 300) {
                    call.reject("HTTP " + statusCode + ": " + responseBody);
                    return;
                }

                JSObject result = new JSObject();
                result.put("status", statusCode);
                result.put("body", responseBody);
                call.resolve(result);
            } catch (Exception exception) {
                call.reject(exception.getMessage());
            } finally {
                if (connection != null) {
                    connection.disconnect();
                }
            }
        });
    }

    private String readResponseBody(InputStream inputStream) {
        if (inputStream == null) {
            return "";
        }
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
            StringBuilder builder = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line);
            }
            return builder.toString();
        } catch (Exception exception) {
            return "";
        }
    }
}
