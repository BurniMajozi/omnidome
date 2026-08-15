"use client";

import { useState, useEffect, useRef } from "react";
import { View, Text, TouchableOpacity, StyleSheet, Alert, ScrollView, TextInput, ActivityIndicator } from "react-native";
import { CameraView, useCameraPermissions, type CameraCapturedPicture } from "expo-camera";
import * as ImagePicker from "expo-image-picker";
import * as Notifications from 'expo-notifications';
import { useRouter } from "expo-router";

// Base URL for the customer API. Mirrors NEXT_PUBLIC_API_URL used by the web client.
const API_BASE = process.env.EXPO_PUBLIC_API_URL || "http://localhost:8000";
const RICA_ENDPOINT = `${API_BASE}/portal/rica/submit`;

interface NativeBridge {
  setSecureValue: (key: string, value: string) => Promise<void>;
  getSecureValue: (key: string) => Promise<string | null>;
  deleteSecureValue: (key: string) => Promise<void>;
  getPushToken: () => Promise<string>;
  requestNotificationPermissions: () => Promise<string>;
  getAppVersion: () => string;
  getPlatform: () => string;
}

declare global {
  interface Window {
    __NATIVE_BRIDGE__?: NativeBridge;
  }
}

const DOC_TYPE_MAP = {
  id: "south_african_id",
  passport: "passport",
  smart_id: "smart_id",
} as const;

export default function RicaCapturePage() {
  const router = useRouter();
  const [permission, requestPermission] = useCameraPermissions();
  const [capturing, setCapturing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [idNumber, setIdNumber] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [documentType, setDocumentType] = useState<"id" | "passport" | "smart_id">("id");
  const [capturedImages, setCapturedImages] = useState<string[]>([]);
  const cameraRef = useRef<CameraView>(null);

  useEffect(() => {
    registerForPushNotifications();
  }, []);

  const registerForPushNotifications = async () => {
    try {
      const bridge = typeof window !== "undefined" ? window.__NATIVE_BRIDGE__ : null;
      if (bridge) {
        const status = await bridge.requestNotificationPermissions();
        if (status === "granted") {
          const token = await await bridge.getPushToken();
          // Send token to API
          console.log("Push token:", token);
        }
      }
    } catch (err) {
      console.error("Push notification registration failed:", err);
    }
  };

  const captureDocument = async () => {
    if (!permission?.granted) {
      await requestPermission();
      return;
    }
    setCapturing(true);
  };

  const takePicture = async () => {
    try {
      const photo: CameraCapturedPicture | undefined = cameraRef.current
        ? await cameraRef.current.takePictureAsync({ quality: 0.8 })
        : undefined;
      if (photo?.uri) {
        setCapturedImages((prev) => [...prev, photo.uri]);
      }
    } catch (err) {
      console.error("Failed to capture document:", err);
      Alert.alert("Capture failed", "Could not capture the document. Please try again or use the gallery.");
    } finally {
      setCapturing(false);
    }
  };

  const pickFromGallery = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true,
      aspect: [4, 3],
      quality: 0.8,
    });
    if (!result.canceled && result.assets[0]) {
      setCapturedImages((prev) => [...prev, result.assets[0].uri]);
    }
  };

  const submitRica = async () => {
    // Require at least one REAL captured/gallery image (a valid file:// or content:// URI).
    const realImages = capturedImages.filter(
      (uri) => uri && !uri.startsWith("captured_image_uri")
    );
    if (!idNumber || !firstName || !lastName || realImages.length === 0) {
      Alert.alert("Missing Information", "Please fill in all fields and capture at least one document image.");
      return;
    }

    try {
      setSubmitting(true);

      const bridge = typeof window !== "undefined" ? window.__NATIVE_BRIDGE__ : null;
      const token = bridge ? await bridge.getSecureValue("access_token") : null;

      const formData = new FormData();
      formData.append("id_number", idNumber);
      formData.append("first_name", firstName);
      formData.append("last_name", lastName);
      formData.append("document_type", DOC_TYPE_MAP[documentType]);

      realImages.forEach((uri, i) => {
        formData.append(`document_${i}`, {
          uri,
          type: "image/jpeg",
          name: `document_${i}.jpg`,
        } as any);
      });

      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const response = await fetch(RICA_ENDPOINT, {
        method: "POST",
        headers,
        body: formData,
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody?.message || `Submission failed (${response.status})`);
      }

      Alert.alert("Success", "RICA verification submitted. You will be notified once verified.");
      router.back();
    } catch (err) {
      console.error("RICA submission error:", err);
      Alert.alert(
        "Error",
        err instanceof Error ? err.message : "Failed to submit RICA verification. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (capturing) {
    return (
      <View style={styles.cameraContainer}>
        <CameraView ref={cameraRef} style={styles.camera} facing="back">
          <View style={styles.cameraOverlay}>
            <TouchableOpacity style={styles.captureButton} onPress={takePicture}>
              <View style={styles.captureButtonInner} />
            </TouchableOpacity>
            <TouchableOpacity style={styles.cancelButton} onPress={() => setCapturing(false)}>
              <Text style={styles.cancelText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </CameraView>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>RICA Verification</Text>
      <Text style={styles.subtitle}>Capture your identity document for verification</Text>

      <View style={styles.section}>
        <Text style={styles.label}>Document Type</Text>
        <View style={styles.segmented}>
          {(["id", "passport", "smart_id"] as const).map((type) => (
            <TouchableOpacity key={type} style={[styles.segment, documentType === type && styles.segmentActive]}
              onPress={() => setDocumentType(type)}>
              <Text style={[styles.segmentText, documentType === type && styles.segmentTextActive]}>
                {type === "id" ? "SA ID" : type === "passport" ? "Passport" : "Smart ID"}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.label}>ID Number</Text>
        <TextInput style={styles.input} value={idNumber} onChangeText={setIdNumber} placeholder="Enter ID number" keyboardType="numeric" />
      </View>

      <View style={styles.section}>
        <Text style={styles.label}>First Name</Text>
        <TextInput style={styles.input} value={firstName} onChangeText={setFirstName} placeholder="As on document" />
      </View>

      <View style={styles.section}>
        <Text style={styles.label}>Last Name</Text>
        <TextInput style={styles.input} value={lastName} onChangeText={setLastName} placeholder="As on document" />
      </View>

      <View style={styles.section}>
        <Text style={styles.label}>Document Images ({capturedImages.length})</Text>
        <View style={styles.buttonRow}>
          <TouchableOpacity style={styles.actionButton} onPress={captureDocument}>
            <Text style={styles.actionButtonText}>📷 Capture</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionButton} onPress={pickFromGallery}>
            <Text style={styles.actionButtonText}>🖼 Gallery</Text>
          </TouchableOpacity>
        </View>
      </View>

      <TouchableOpacity
        style={[styles.submitButton, submitting && { opacity: 0.7 }]}
        onPress={submitRica}
        disabled={submitting}
      >
        {submitting ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.submitButtonText}>Submit for Verification</Text>
        )}
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f8fafc", padding: 20 },
  title: { fontSize: 24, fontWeight: "bold", color: "#0f172a", marginBottom: 4 },
  subtitle: { fontSize: 14, color: "#64748b", marginBottom: 24 },
  section: { marginBottom: 20 },
  label: { fontSize: 13, fontWeight: "600", color: "#374151", marginBottom: 8 },
  segmented: { flexDirection: "row", backgroundColor: "#f1f5f9", borderRadius: 8, padding: 2 },
  segment: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: 6 },
  segmentActive: { backgroundColor: "#2563eb" },
  segmentText: { fontSize: 12, color: "#64748b", fontWeight: "500" },
  segmentTextActive: { color: "#fff" },
  input: { backgroundColor: "#fff", borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 8, padding: 12, fontSize: 14, color: "#0f172a" },
  buttonRow: { flexDirection: "row", gap: 12 },
  actionButton: { flex: 1, backgroundColor: "#fff", borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 8, padding: 14, alignItems: "center" },
  actionButtonText: { fontSize: 14, color: "#374151", fontWeight: "500" },
  submitButton: { backgroundColor: "#2563eb", borderRadius: 8, padding: 16, alignItems: "center", marginTop: 8, marginBottom: 40 },
  submitButtonText: { color: "#fff", fontSize: 15, fontWeight: "600" },
  cameraContainer: { flex: 1, backgroundColor: "#000" },
  camera: { flex: 1 },
  cameraOverlay: { flex: 1, backgroundColor: "transparent", justifyContent: "flex-end", alignItems: "center", paddingBottom: 40 },
  captureButton: { width: 70, height: 70, borderRadius: 35, backgroundColor: "rgba(255,255,255,0.3)", justifyContent: "center", alignItems: "center" },
  captureButtonInner: { width: 56, height: 56, borderRadius: 28, backgroundColor: "#fff" },
  cancelButton: { position: "absolute", top: 50, right: 20 },
  cancelText: { color: "#fff", fontSize: 16 },
});
