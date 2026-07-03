"use client";

import { useEffect, useRef } from "react";

interface Star {
  x: number;
  y: number;
  baseX: number;
  baseY: number;
  size: number;
  length: number;
  angle: number;
  opacity: number;
  twinkleSpeed: number;
  twinklePhase: number;
  orbitAngle: number;
  orbitRadius: number;
  orbitSpeed: number;
  color: string;
  connectionIndex: number;
}

/**
 * OmniDome galactic dome starfield — ported from the marketing landing page
 * (apps/web/app/page.tsx) and tuned down for mobile WebViews:
 * 250 stars instead of 800, no mouse interaction, devicePixelRatio capped.
 *
 * Renders as a fixed, full-viewport canvas behind all content. Pair with
 * translucent surface colors so the dome shows through.
 */
export function GalacticDomeBackground({ variant = "dark" }: { variant?: "dark" | "light" }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const starsRef = useRef<Star[]>([]);
  const frameRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const isDark = variant === "dark";
    const colors = isDark
      ? ["79, 70, 229", "99, 102, 241", "129, 140, 248", "139, 92, 246", "59, 130, 246", "100, 116, 139"]
      : ["67, 56, 202", "79, 70, 229", "99, 102, 241", "124, 58, 237", "37, 99, 235", "71, 85, 105"];
    const opacityMultiplier = isDark ? 1 : 2.2;
    const STAR_COUNT = 250;
    const ACCENT_COUNT = 12;

    const initStars = () => {
      starsRef.current = [];
      const centerX = canvas.width / 2;
      const centerY = canvas.height * 0.65;
      const domeWidth = canvas.width * 1.2;
      const domeHeight = canvas.height * 0.9;

      for (let i = 0; i < STAR_COUNT; i++) {
        const angle = Math.random() * Math.PI;
        const radiusFactor = Math.pow(Math.random(), 0.5);
        const baseX = centerX + Math.cos(angle) * radiusFactor * domeWidth * 0.5;
        const baseY = centerY - Math.sin(angle) * radiusFactor * domeHeight * 0.6;
        const streakAngle = Math.atan2(centerY - baseY, centerX - baseX) + (Math.random() - 0.5) * 0.5;

        starsRef.current.push({
          x: baseX,
          y: baseY,
          baseX,
          baseY,
          size: 0.8 + Math.random() * 1.2,
          length: 4 + Math.random() * 10,
          angle: streakAngle,
          opacity: (0.15 + Math.random() * 0.25) * opacityMultiplier,
          twinkleSpeed: 0.01 + Math.random() * 0.02,
          twinklePhase: Math.random() * Math.PI * 2,
          orbitAngle: Math.random() * Math.PI * 2,
          orbitRadius: 1 + Math.random() * 4,
          orbitSpeed: 0.002 + Math.random() * 0.006,
          color: colors[Math.floor(Math.random() * colors.length)],
          connectionIndex: Math.random() > 0.7 ? Math.floor(Math.random() * STAR_COUNT) : -1,
        });
      }

      for (let i = 0; i < ACCENT_COUNT; i++) {
        const angle = Math.random() * Math.PI;
        const radiusFactor = Math.random() * 0.7;
        const baseX = centerX + Math.cos(angle) * radiusFactor * domeWidth * 0.4;
        const baseY = centerY - Math.sin(angle) * radiusFactor * domeHeight * 0.5;
        starsRef.current.push({
          x: baseX,
          y: baseY,
          baseX,
          baseY,
          size: 2 + Math.random() * 1.5,
          length: 0,
          angle: 0,
          opacity: (0.35 + Math.random() * 0.25) * opacityMultiplier,
          twinkleSpeed: 0.015 + Math.random() * 0.02,
          twinklePhase: Math.random() * Math.PI * 2,
          orbitAngle: Math.random() * Math.PI * 2,
          orbitRadius: 2 + Math.random() * 3,
          orbitSpeed: 0.004 + Math.random() * 0.006,
          color: "129, 140, 248",
          connectionIndex: -1,
        });
      }
    };

    const resizeCanvas = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      initStars();
    };
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    let time = 0;
    const animate = () => {
      time += 1;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      ctx.lineWidth = 0.8;
      starsRef.current.forEach((star, index) => {
        if (star.connectionIndex >= 0 && star.connectionIndex < starsRef.current.length && star.connectionIndex !== index) {
          const target = starsRef.current[star.connectionIndex];
          const dist = Math.hypot(star.x - target.x, star.y - target.y);
          if (dist < 250) {
            const lineOpacity = (1 - dist / 250) * 0.15;
            ctx.beginPath();
            ctx.moveTo(star.x, star.y);
            ctx.lineTo(target.x, target.y);
            ctx.strokeStyle = `rgba(99, 102, 241, ${lineOpacity})`;
            ctx.stroke();
          }
        }
      });

      starsRef.current.forEach((star) => {
        star.orbitAngle += star.orbitSpeed;
        star.x = star.baseX + Math.cos(star.orbitAngle) * star.orbitRadius;
        star.y = star.baseY + Math.sin(star.orbitAngle) * star.orbitRadius * 0.5;

        const twinkle = 0.6 + 0.4 * Math.sin(time * star.twinkleSpeed + star.twinklePhase);
        const alpha = star.opacity * twinkle;

        if (star.length > 0) {
          ctx.beginPath();
          ctx.moveTo(star.x, star.y);
          ctx.lineTo(star.x + Math.cos(star.angle) * star.length, star.y + Math.sin(star.angle) * star.length);
          ctx.strokeStyle = `rgba(${star.color}, ${alpha})`;
          ctx.lineWidth = star.size;
          ctx.stroke();
        } else {
          ctx.beginPath();
          ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(${star.color}, ${alpha})`;
          ctx.fill();
        }
      });

      frameRef.current = requestAnimationFrame(animate);
    };
    frameRef.current = requestAnimationFrame(animate);

    return () => {
      window.removeEventListener("resize", resizeCanvas);
      if (frameRef.current !== undefined) cancelAnimationFrame(frameRef.current);
    };
  }, [variant]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="fixed inset-0 -z-10 pointer-events-none"
      style={{ background: variant === "dark" ? "radial-gradient(ellipse at 50% 65%, #14143a 0%, #0a0a1f 60%, #050510 100%)" : "radial-gradient(ellipse at 50% 65%, #eef0ff 0%, #f8f9ff 60%, #ffffff 100%)" }}
    />
  );
}
