"use client";

import React, { useState } from "react";
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
} from "react-native";
import {
  Home,
  Wifi,
  Camera,
  Lock,
  Lightbulb,
  Thermometer,
  Shield,
  Zap,
  CheckCircle2,
  Circle,
  ChevronRight,
  TrendingUp,
  Radio,
} from "lucide-react-native";

const IOT_PACKAGES = [
  {
    id: "basic",
    name: "Basic Smart Home",
    icon: Shield,
    color: "#60a5fa",
    devices: ["2x Door/Window Sensors", "1x Smart Camera", "1x Smart Plug"],
    monthlyRevenue: 149,
    description: "Entry-level security and monitoring",
  },
  {
    id: "standard",
    name: "Standard Smart Home",
    icon: Lock,
    color: "#a855f7",
    devices: [
      "Basic package +",
      "2x Smart Locks",
      "4x Smart Bulbs",
      "1x Motion Sensor",
    ],
    monthlyRevenue: 349,
    description: "Full security with lighting control",
  },
  {
    id: "premium",
    name: "Premium Smart Home",
    icon: Zap,
    color: "#f59e0b",
    devices: [
      "Standard package +",
      "Smart Thermostat",
      "Energy Monitor",
      "Smart Blinds (2x)",
      "Hub + Voice Assistant",
    ],
    monthlyRevenue: 649,
    description: "Complete home automation with energy management",
  },
];

const PROPERTY_TYPES = [
  { id: "house", label: "House", icon: "🏠" },
  { id: "apartment", label: "Apartment", icon: "🏢" },
  { id: "commercial", label: "Commercial", icon: "🏪" },
];

const WIRING_TYPES = [
  { id: "fiber", label: "Fiber Ready", score: 30 },
  { id: "ethernet", label: "Ethernet Wired", score: 25 },
  { id: "coax", label: "Coax Only", score: 10 },
  { id: "none", label: "No Wiring", score: 0 },
];

const SMART_DEVICE_OPTIONS = [
  "Smart TV",
  "Smart Speaker",
  "Smart Thermostat",
  "Smart Lock",
  "Smart Lights",
  "Security Camera",
  "Video Doorbell",
  "Smart Plug",
  "Robot Vacuum",
  "Smart Blinds",
];

export default function PropertyIoTPage() {
  const [wiringType, setWiringType] = useState<string>("");
  const [selectedDevices, setSelectedDevices] = useState<string[]>([]);
  const [estimatedRooms, setEstimatedRooms] = useState("");
  const [propertyType, setPropertyType] = useState<string>("");
  const [expandedPackage, setExpandedPackage] = useState<string | null>(null);

  const toggleDevice = (device: string) => {
    setSelectedDevices((prev) =>
      prev.includes(device) ? prev.filter((d) => d !== device) : [...prev, device]
    );
  };

  // Calculate IoT Readiness Score
  const wiringScore = WIRING_TYPES.find((w) => w.id === wiringType)?.score || 0;
  const deviceScore = Math.min(selectedDevices.length * 5, 25);
  const roomScore = Math.min(Number(estimatedRooms) * 3, 15);
  const propertyScore = propertyType === "house" ? 20 : propertyType === "apartment" ? 15 : 10;
  const totalScore = Math.min(wiringScore + deviceScore + roomScore + propertyScore, 100);

  const getScoreColor = (score: number) => {
    if (score >= 70) return "#10b981";
    if (score >= 40) return "#f59e0b";
    return "#ef4444";
  };

  const getRecommendedPackage = () => {
    if (totalScore >= 70) return IOT_PACKAGES[2];
    if (totalScore >= 40) return IOT_PACKAGES[1];
    return IOT_PACKAGES[0];
  };

  const recommendedPackage = getRecommendedPackage();
  const estimatedUpsell = recommendedPackage.monthlyRevenue;

  return (
    <ScrollView className="flex-1 bg-slate-900">
      {/* Header */}
      <View className="px-4 pt-6 pb-4">
        <Text className="text-2xl font-bold text-white">Property IoT Readiness</Text>
        <Text className="text-slate-400 text-sm mt-1">
          Assess property potential for smart home packages
        </Text>
      </View>

      {/* Readiness Score Card */}
      <View className="mx-4 mb-4 rounded-xl bg-slate-800 border border-slate-700 p-5">
        <View className="flex-row items-center justify-between mb-4">
          <Text className="text-lg font-semibold text-white">IoT Readiness Score</Text>
          <View
            className="w-16 h-16 rounded-full items-center justify-center"
            style={{ backgroundColor: getScoreColor(totalScore) + "20" }}
          >
            <Text
              className="text-2xl font-bold"
              style={{ color: getScoreColor(totalScore) }}
            >
              {totalScore}
            </Text>
          </View>
        </View>

        {/* Score Breakdown */}
        <View className="space-y-3">
          <View className="flex-row items-center justify-between">
            <Text className="text-slate-300 text-sm">Wiring Infrastructure</Text>
            <Text className="text-slate-400 text-sm">{wiringScore}/30</Text>
          </View>
          <View className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <View
              className="h-full rounded-full"
              style={{
                width: `${(wiringScore / 30) * 100}%`,
                backgroundColor: "#60a5fa",
              }}
            />
          </View>

          <View className="flex-row items-center justify-between">
            <Text className="text-slate-300 text-sm">Existing Smart Devices</Text>
            <Text className="text-slate-400 text-sm">{deviceScore}/25</Text>
          </View>
          <View className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <View
              className="h-full rounded-full"
              style={{
                width: `${(deviceScore / 25) * 100}%`,
                backgroundColor: "#a855f7",
              }}
            />
          </View>

          <View className="flex-row items-center justify-between">
            <Text className="text-slate-300 text-sm">Property Size (Rooms)</Text>
            <Text className="text-slate-400 text-sm">{roomScore}/15</Text>
          </View>
          <View className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <View
              className="h-full rounded-full"
              style={{
                width: `${(roomScore / 15) * 100}%`,
                backgroundColor: "#10b981",
              }}
            />
          </View>

          <View className="flex-row items-center justify-between">
            <Text className="text-slate-300 text-sm">Property Type</Text>
            <Text className="text-slate-400 text-sm">{propertyScore}/20</Text>
          </View>
          <View className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <View
              className="h-full rounded-full"
              style={{
                width: `${(propertyScore / 20) * 100}%`,
                backgroundColor: "#f59e0b",
              }}
            />
          </View>
        </View>
      </View>

      {/* Assessment Form */}
      <View className="mx-4 mb-4 rounded-xl bg-slate-800 border border-slate-700 p-5">
        <Text className="text-lg font-semibold text-white mb-4">
          Property Assessment
        </Text>

        {/* Property Type */}
        <Text className="text-slate-300 text-sm font-medium mb-2">
          Property Type
        </Text>
        <View className="flex-row gap-2 mb-4">
          {PROPERTY_TYPES.map((type) => (
            <TouchableOpacity
              key={type.id}
              onPress={() => setPropertyType(type.id)}
              className={`flex-1 py-3 rounded-lg items-center border ${
                propertyType === type.id
                  ? "bg-emerald-500/20 border-emerald-500"
                  : "bg-slate-700/50 border-slate-600"
              }`}
            >
              <Text className="text-xl">{type.icon}</Text>
              <Text
                className={`text-xs mt-1 ${
                  propertyType === type.id ? "text-emerald-400" : "text-slate-400"
                }`}
              >
                {type.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Wiring Type */}
        <Text className="text-slate-300 text-sm font-medium mb-2">
          Existing Wiring
        </Text>
        <View className="space-y-2 mb-4">
          {WIRING_TYPES.map((wiring) => (
            <TouchableOpacity
              key={wiring.id}
              onPress={() => setWiringType(wiring.id)}
              className={`flex-row items-center justify-between p-3 rounded-lg border ${
                wiringType === wiring.id
                  ? "bg-blue-500/20 border-blue-500"
                  : "bg-slate-700/50 border-slate-600"
              }`}
            >
              <View className="flex-row items-center gap-3">
                <Wifi
                  size={18}
                  color={wiringType === wiring.id ? "#60a5fa" : "#94a3b8"}
                />
                <Text
                  className={`text-sm ${
                    wiringType === wiring.id ? "text-blue-400" : "text-slate-300"
                  }`}
                >
                  {wiring.label}
                </Text>
              </View>
              {wiringType === wiring.id && (
                <CheckCircle2 size={18} color="#60a5fa" />
              )}
            </TouchableOpacity>
          ))}
        </View>

        {/* Estimated Rooms */}
        <Text className="text-slate-300 text-sm font-medium mb-2">
          Estimated Rooms
        </Text>
        <TextInput
          value={estimatedRooms}
          onChangeText={setEstimatedRooms}
          placeholder="e.g. 5"
          placeholderTextColor="#64748b"
          keyboardType="numeric"
          className="bg-slate-700/50 border border-slate-600 rounded-lg px-4 py-3 text-white text-sm mb-4"
        />

        {/* Existing Smart Devices */}
        <Text className="text-slate-300 text-sm font-medium mb-2">
          Existing Smart Devices
        </Text>
        <View className="flex-row flex-wrap gap-2 mb-2">
          {SMART_DEVICE_OPTIONS.map((device) => {
            const selected = selectedDevices.includes(device);
            return (
              <TouchableOpacity
                key={device}
                onPress={() => toggleDevice(device)}
                className={`flex-row items-center gap-1.5 px-3 py-1.5 rounded-full border ${
                  selected
                    ? "bg-purple-500/20 border-purple-500"
                    : "bg-slate-700/50 border-slate-600"
                }`}
              >
                {selected ? (
                  <CheckCircle2 size={14} color="#a855f7" />
                ) : (
                  <Circle size={14} color="#64748b" />
                )}
                <Text
                  className={`text-xs ${
                    selected ? "text-purple-400" : "text-slate-400"
                  }`}
                >
                  {device}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      {/* Recommended Package */}
      <View className="mx-4 mb-4 rounded-xl bg-slate-800 border border-slate-700 p-5">
        <View className="flex-row items-center gap-2 mb-3">
          <TrendingUp size={20} color="#10b981" />
          <Text className="text-lg font-semibold text-white">
            Recommended Package
          </Text>
        </View>

        <TouchableOpacity
          onPress={() =>
            setExpandedPackage(
              expandedPackage === recommendedPackage.id ? null : recommendedPackage.id
            )
          }
          className="rounded-lg bg-slate-700/50 border border-slate-600 p-4"
        >
          <View className="flex-row items-center justify-between">
            <View className="flex-row items-center gap-3">
              <View
                className="w-10 h-10 rounded-lg items-center justify-center"
                style={{ backgroundColor: recommendedPackage.color + "20" }}
              >
                <recommendedPackage.icon size={20} color={recommendedPackage.color} />
              </View>
              <View>
                <Text className="text-white font-medium">
                  {recommendedPackage.name}
                </Text>
                <Text className="text-slate-400 text-xs">
                  {recommendedPackage.description}
                </Text>
              </View>
            </View>
            <View className="flex-row items-center gap-2">
              <Text className="text-emerald-400 font-bold text-lg">
                R{recommendedPackage.monthlyRevenue}
              </Text>
              <Text className="text-slate-500 text-xs">/mo</Text>
              <ChevronRight size={18} color="#64748b" />
            </View>
          </View>

          {expandedPackage === recommendedPackage.id && (
            <View className="mt-3 pt-3 border-t border-slate-600">
              <Text className="text-slate-300 text-sm mb-2">Includes:</Text>
              {recommendedPackage.devices.map((device, i) => (
                <View key={i} className="flex-row items-center gap-2 py-1">
                  <CheckCircle2 size={14} color="#10b981" />
                  <Text className="text-slate-400 text-sm">{device}</Text>
                </View>
              ))}
            </View>
          )}
        </TouchableOpacity>
      </View>

      {/* Upsell Potential */}
      <View className="mx-4 mb-4 rounded-xl bg-slate-800 border border-slate-700 p-5">
        <Text className="text-lg font-semibold text-white mb-3">
          Upsell Potential
        </Text>

        <View className="flex-row items-center justify-between p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 mb-3">
          <View>
            <Text className="text-slate-300 text-sm">Estimated Monthly Revenue</Text>
            <Text className="text-emerald-400 text-2xl font-bold">
              R{estimatedUpsell}
            </Text>
          </View>
          <View className="items-end">
            <Text className="text-slate-400 text-xs">Annual Potential</Text>
            <Text className="text-emerald-400 text-lg font-semibold">
              R{(estimatedUpsell * 12).toLocaleString()}
            </Text>
          </View>
        </View>

        <View className="flex-row items-center justify-between p-3 rounded-lg bg-blue-500/10 border border-blue-500/30">
          <View>
            <Text className="text-slate-300 text-sm">Installation Revenue</Text>
            <Text className="text-blue-400 text-2xl font-bold">
              R{Math.round(estimatedUpsell * 2.5)}
            </Text>
          </View>
          <Radio size={24} color="#60a5fa" />
        </View>
      </View>

      {/* All Packages */}
      <View className="mx-4 mb-6 rounded-xl bg-slate-800 border border-slate-700 p-5">
        <Text className="text-lg font-semibold text-white mb-3">
          All IoT Packages
        </Text>

        <View className="space-y-3">
          {IOT_PACKAGES.map((pkg) => (
            <TouchableOpacity
              key={pkg.id}
              onPress={() =>
                setExpandedPackage(expandedPackage === pkg.id ? null : pkg.id)
              }
              className="rounded-lg bg-slate-700/50 border border-slate-600 p-4"
            >
              <View className="flex-row items-center justify-between">
                <View className="flex-row items-center gap-3">
                  <View
                    className="w-10 h-10 rounded-lg items-center justify-center"
                    style={{ backgroundColor: pkg.color + "20" }}
                  >
                    <pkg.icon size={20} color={pkg.color} />
                  </View>
                  <View>
                    <Text className="text-white font-medium">{pkg.name}</Text>
                    <Text className="text-slate-400 text-xs">
                      {pkg.devices.length} devices
                    </Text>
                  </View>
                </View>
                <Text className="text-white font-bold">R{pkg.monthlyRevenue}/mo</Text>
              </View>

              {expandedPackage === pkg.id && (
                <View className="mt-3 pt-3 border-t border-slate-600">
                  {pkg.devices.map((device, i) => (
                    <View key={i} className="flex-row items-center gap-2 py-1">
                      <CheckCircle2 size={14} color={pkg.color} />
                      <Text className="text-slate-400 text-sm">{device}</Text>
                    </View>
                  ))}
                </View>
              )}
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Save Button */}
      <View className="mx-4 mb-8">
        <TouchableOpacity
          onPress={() =>
            Alert.alert(
              "Assessment Saved",
              `Property IoT assessment saved. Readiness Score: ${totalScore}/100. Recommended: ${recommendedPackage.name}`
            )
          }
          className="bg-emerald-500 rounded-xl py-4 items-center"
        >
          <Text className="text-white font-bold text-base">
            Save Assessment
          </Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}
