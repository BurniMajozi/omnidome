"use client";

import { useEffect, useMemo, useRef } from "react";
import { Animated, Dimensions, Easing, StyleSheet, View } from "react-native";
import Svg, { Circle, Defs, Line, RadialGradient, Rect, Stop } from "react-native-svg";

// OmniDome galactic dome starfield — React Native port of the marketing
// landing page canvas (apps/web/app/page.tsx). Static SVG star geometry
// (seeded, so it never reshuffles between renders) split across two layers
// whose opacities pulse out of phase to fake per-star twinkle cheaply.

const COLORS = ["#4f46e5", "#6366f1", "#818cf8", "#8b5cf6", "#3b82f6", "#64748b"];
const STAR_COUNT = 140;
const ACCENT_COUNT = 10;
const CONNECTION_MAX = 30;

// Deterministic LCG so the sky is stable across renders and reloads.
function makeRandom(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

interface StarDef {
  x: number;
  y: number;
  size: number;
  length: number;
  angle: number;
  opacity: number;
  color: string;
  layer: 0 | 1;
}

function buildSky(width: number, height: number) {
  const rand = makeRandom(42);
  const centerX = width / 2;
  const centerY = height * 0.65;
  const domeWidth = width * 1.2;
  const domeHeight = height * 0.9;

  const stars: StarDef[] = [];
  for (let i = 0; i < STAR_COUNT; i++) {
    const angle = rand() * Math.PI;
    const radiusFactor = Math.sqrt(rand());
    const x = centerX + Math.cos(angle) * radiusFactor * domeWidth * 0.5;
    const y = centerY - Math.sin(angle) * radiusFactor * domeHeight * 0.6;
    const streakAngle = Math.atan2(centerY - y, centerX - x) + (rand() - 0.5) * 0.5;
    stars.push({
      x,
      y,
      size: 0.8 + rand() * 1.2,
      length: 4 + rand() * 10,
      angle: streakAngle,
      opacity: 0.15 + rand() * 0.25,
      color: COLORS[Math.floor(rand() * COLORS.length)],
      layer: rand() > 0.5 ? 0 : 1,
    });
  }

  const accents: StarDef[] = [];
  for (let i = 0; i < ACCENT_COUNT; i++) {
    const angle = rand() * Math.PI;
    const radiusFactor = rand() * 0.7;
    accents.push({
      x: centerX + Math.cos(angle) * radiusFactor * domeWidth * 0.4,
      y: centerY - Math.sin(angle) * radiusFactor * domeHeight * 0.5,
      size: 2 + rand() * 1.5,
      length: 0,
      angle: 0,
      opacity: 0.35 + rand() * 0.25,
      color: "#818cf8",
      layer: rand() > 0.5 ? 0 : 1,
    });
  }

  const connections: { x1: number; y1: number; x2: number; y2: number; opacity: number }[] = [];
  for (let i = 0; i < CONNECTION_MAX; i++) {
    const a = stars[Math.floor(rand() * stars.length)];
    const b = stars[Math.floor(rand() * stars.length)];
    const dist = Math.hypot(a.x - b.x, a.y - b.y);
    if (dist > 0 && dist < 250) {
      connections.push({ x1: a.x, y1: a.y, x2: b.x, y2: b.y, opacity: (1 - dist / 250) * 0.15 });
    }
  }

  return { stars: [...stars, ...accents], connections };
}

function StarLayer({ stars, width, height }: { stars: StarDef[]; width: number; height: number }) {
  return (
    <Svg width={width} height={height} style={StyleSheet.absoluteFill} pointerEvents="none">
      {stars.map((s, i) =>
        s.length > 0 ? (
          <Line
            key={i}
            x1={s.x}
            y1={s.y}
            x2={s.x + Math.cos(s.angle) * s.length}
            y2={s.y + Math.sin(s.angle) * s.length}
            stroke={s.color}
            strokeWidth={s.size}
            strokeOpacity={s.opacity}
          />
        ) : (
          <Circle key={i} cx={s.x} cy={s.y} r={s.size} fill={s.color} fillOpacity={s.opacity} />
        ),
      )}
    </Svg>
  );
}

export function GalacticDomeBackground() {
  const { width, height } = Dimensions.get("window");
  const sky = useMemo(() => buildSky(width, height), [width, height]);
  const pulseA = useRef(new Animated.Value(1)).current;
  const pulseB = useRef(new Animated.Value(0.55)).current;

  useEffect(() => {
    const loop = (value: Animated.Value, from: number, to: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(value, { toValue: to, duration: 2600, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
          Animated.timing(value, { toValue: from, duration: 2600, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        ]),
      );
    const a = loop(pulseA, 1, 0.55);
    const b = loop(pulseB, 0.55, 1);
    a.start();
    b.start();
    return () => {
      a.stop();
      b.stop();
    };
  }, [pulseA, pulseB]);

  const layer0 = sky.stars.filter((s) => s.layer === 0);
  const layer1 = sky.stars.filter((s) => s.layer === 1);

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      <Svg width={width} height={height} style={StyleSheet.absoluteFill}>
        <Defs>
          <RadialGradient id="dome" cx="50%" cy="65%" rx="80%" ry="70%">
            <Stop offset="0%" stopColor="#14143a" />
            <Stop offset="60%" stopColor="#0a0a1f" />
            <Stop offset="100%" stopColor="#050510" />
          </RadialGradient>
        </Defs>
        <Rect x={0} y={0} width={width} height={height} fill="url(#dome)" />
        {sky.connections.map((c, i) => (
          <Line key={i} x1={c.x1} y1={c.y1} x2={c.x2} y2={c.y2} stroke="#6366f1" strokeWidth={0.8} strokeOpacity={c.opacity} />
        ))}
      </Svg>
      <Animated.View style={[StyleSheet.absoluteFill, { opacity: pulseA }]}>
        <StarLayer stars={layer0} width={width} height={height} />
      </Animated.View>
      <Animated.View style={[StyleSheet.absoluteFill, { opacity: pulseB }]}>
        <StarLayer stars={layer1} width={width} height={height} />
      </Animated.View>
    </View>
  );
}
