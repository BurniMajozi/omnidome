// Expo entry point for native builds (Android/iOS/Huawei)
// This wraps the Next.js app for native deployment via Expo WebView
// and provides native module bridges for camera, notifications, secure store, location

import { registerRootComponent } from 'expo';
import { ExpoRoot } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';

// Prevent auto-hide of splash screen
SplashScreen.preventAutoHideAsync();

// Configure notification behavior
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

// Native module bridge — exposes native APIs to the web layer
const nativeBridge = {
  // Secure token storage
  async setSecureValue(key: string, value: string) {
    await SecureStore.setItemAsync(key, value);
  },
  async getSecureValue(key: string) {
    return await SecureStore.getItemAsync(key);
  },
  async deleteSecureValue(key: string) {
    await SecureStore.deleteItemAsync(key);
  },

  // Notifications
  async getPushToken() {
    const { data } = await Notifications.getExpoPushTokenAsync();
    return data;
  },

  async requestNotificationPermissions() {
    const { status } = await Notifications.requestPermissionsAsync();
    return status;
  },

  // App version
  getAppVersion() {
    return '1.0.0';
  },

  getPlatform() {
    return Platform.OS;
  },
};

// Expose bridge to window for web layer access
if (typeof window !== 'undefined') {
  (window as any).__NATIVE_BRIDGE__ = nativeBridge;
}

export function App() {
  useEffect(() => {
    SplashScreen.hideAsync();
  }, []);

  const ctx = require.context('./app');
  return <ExpoRoot context={ctx} />;
}

registerRootComponent(App);
