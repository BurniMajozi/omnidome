import { existsSync } from 'node:fs';
import type { ExpoConfig, ConfigContext } from 'expo/config';

// EAS project ID is supplied via environment (set with `eas secret:create EAS_PROJECT_ID <id>`
// or export it locally). It is intentionally NOT hardcoded here — a fake placeholder would
// silently break OTA updates / EAS Submit. If unset, EAS build/submit will fail loudly.
const EAS_PROJECT_ID = process.env.EAS_PROJECT_ID;

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: 'OmniDome',
  slug: 'omnidome-customer',
  version: '1.0.0',
  orientation: 'portrait',
  icon: './assets/icon.png',
  userInterfaceStyle: 'automatic',
  newArchEnabled: true,

  splash: {
    image: './assets/splash.png',
    resizeMode: 'contain',
    backgroundColor: '#2563eb',
  },

  assetBundlePatterns: ['**/*'],

  ios: {
    supportsTablet: true,
    bundleIdentifier: 'com.omnidome.customer',
    buildNumber: '1',
    infoPlist: {
      NSCameraUsageDescription:
        'This app uses the camera to capture ID documents for RICA verification.',
      NSPhotoLibraryUsageDescription:
        'This app accesses your photo library to upload ID documents for RICA verification.',
      NSLocationWhenInUseUsageDescription:
        'This app uses your location to check fibre coverage in your area.',
      UIBackgroundModes: ['remote-notification'],
    },
    config: {
      usesNonExemptEncryption: false,
    },
  },

  android: {
    adaptiveIcon: {
      foregroundImage: './assets/adaptive-icon.png',
      backgroundColor: '#2563eb',
    },
    package: 'com.omnidome.customer',
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
    [
      'expo-camera',
      {
        cameraPermission:
          'Allow $(PRODUCT_NAME) to access your camera for RICA document capture.',
      },
    ],
    [
      'expo-image-picker',
      {
        photosPermission:
          'Allow $(PRODUCT_NAME) to access your photos for RICA document upload.',
      },
    ],
    [
      'expo-notifications',
      {
        icon: './assets/notification-icon.png',
        color: '#2563eb',
      },
    ],
    [
      'expo-secure-store',
      {
        faceIDPermission:
          'Allow $(PRODUCT_NAME) to use Face ID to securely store your login credentials.',
      },
    ],
    [
      'expo-location',
      {
        locationWhenInUsePermission:
          'Allow $(PRODUCT_NAME) to use your location to check fibre coverage.',
      },
    ],
  ],

  experiments: {
    typedRoutes: true,
  },

  extra: {
    router: {
      origin: false,
    },
    eas: {
      // Provided at build time via EAS_PROJECT_ID (set in EAS secrets / .env).
      // Never hardcode the real ID — it is account/project specific.
      projectId: EAS_PROJECT_ID ?? '',
    },
  },

  runtimeVersion: {
    policy: 'appVersion',
  },

  updates: {
    url: EAS_PROJECT_ID
      ? `https://u.expo.dev/${EAS_PROJECT_ID}`
      : 'https://u.expo.dev/',
    checkAutomatically: 'ON_LOAD',
    fallbackToCacheTimeout: 0,
  },
});
