import { existsSync } from 'node:fs';
import type { ExpoConfig, ConfigContext } from 'expo/config';

// EAS project ID is supplied via environment (set with `eas secret:create EAS_PROJECT_ID <id>`
// or export it locally). It is intentionally NOT hardcoded here — a fake placeholder would
// silently break OTA updates / EAS Submit. If unset, EAS build/submit will fail loudly.
const EAS_PROJECT_ID = process.env.EAS_PROJECT_ID;

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: 'OmniDome Field Sales',
  slug: 'omnidome-field-sales',
  version: '1.0.0',
  orientation: 'portrait',
  icon: './assets/icon.png',
  userInterfaceStyle: 'automatic',
  newArchEnabled: true,

  splash: {
    image: './assets/splash.png',
    resizeMode: 'contain',
    backgroundColor: '#10b981',
  },

  assetBundlePatterns: ['**/*'],

  ios: {
    supportsTablet: true,
    bundleIdentifier: 'com.omnidome.fieldsales',
    buildNumber: '1',
    infoPlist: {
      NSCameraUsageDescription:
        'This app uses the camera to capture site photos and scan barcodes.',
      NSLocationWhenInUseUsageDescription:
        'This app uses your location for field visit tracking and navigation.',
      UIBackgroundModes: ['remote-notification'],
    },
    config: {
      usesNonExemptEncryption: false,
    },
  },

  android: {
    adaptiveIcon: {
      foregroundImage: './assets/adaptive-icon.png',
      backgroundColor: '#10b981',
    },
    package: 'com.omnidome.fieldsales',
    versionCode: 1,
    permissions: [
      'CAMERA',
      'READ_EXTERNAL_STORAGE',
      'WRITE_EXTERNAL_STORAGE',
      'ACCESS_FINE_LOCATION',
      'ACCESS_COARSE_LOCATION',
      'RECEIVE_BOOT_COMPLETED',
      'VIBRATE',
    ],
    // FCM config is optional for local APK builds — only wired when the file exists.
    ...(existsSync('./google-services.json') ? { googleServicesFile: './google-services.json' } : {}),
    softwareKeyboardLayoutMode: 'pan',
  },

  web: {
    favicon: './assets/favicon.png',
    bundler: 'metro',
  },

  plugins: [
    'expo-router',
    'expo-secure-store',
    [
      'expo-notifications',
      {
        icon: './assets/notification-icon.png',
        color: '#10b981',
        sounds: ['./assets/notification_sound.wav'],
      },
    ],
    'expo-file-system',
  ],

  experiments: {
    typedRoutes: true,
  },

  extra: {
    router: {
      origin: false,
    },
    eas: {
      projectId: EAS_PROJECT_ID,
    },
  },

  runtimeVersion: {
    policy: 'appVersion',
  },

  updates: {
    url: EAS_PROJECT_ID ? `https://u.expo.dev/${EAS_PROJECT_ID}` : undefined,
    checkAutomatically: 'ON_LOAD',
    fallbackToCacheTimeout: 0,
  },
});
