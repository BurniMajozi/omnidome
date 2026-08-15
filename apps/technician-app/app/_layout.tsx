"use client";

import { Stack, Redirect } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { View } from 'react-native';
import { GalacticDomeBackground } from '../components/galactic-dome-background';
import { useAuthStore } from '../lib/stores/auth-store';

export default function RootLayout() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  // Gate the whole app behind authentication.
  if (!isAuthenticated) {
    return <Redirect href="/login" />;
  }

  return (
    <View style={{ flex: 1, backgroundColor: '#050510' }}>
      <GalacticDomeBackground />
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          // Transparent screens so the galactic dome shows through everywhere.
          contentStyle: { backgroundColor: 'transparent' },
        }}
      >
        <Stack.Screen name="(tabs)" />
      </Stack>
    </View>
  );
}
