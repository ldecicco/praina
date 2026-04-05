package app.praina.mobile;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(FcmBridgePlugin.class);
        super.onCreate(savedInstanceState);
    }
}
