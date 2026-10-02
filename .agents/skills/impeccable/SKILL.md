---
name: impeccable
description: "Design guidance and AI frontend toolkit based on Paul Bakaus's Impeccable standard. Provides 25 design commands (/craft, /shape, /critique, /audit, /polish, /bolder, /quieter, /distill, /harden, /animate, /colorize, /typeset, /layout, /delight) and 61 deterministic detector rules to eliminate AI tells and craft production-grade web interfaces."
---

# Impeccable AI Design Skill

Impeccable equips coding agents with a professional frontend design vocabulary and anti-pattern enforcement to produce intentional, production-grade user interfaces rather than generic "AI slop".

## Core Commands

When working on UI components, pages, or styling, apply these Impeccable commands:

| Command | Action |
| :--- | :--- |
| `/craft` | Full shape-then-build workflow with visual iteration |
| `/init` | One-time project setup: writes `PRODUCT.md` and aligns on durable product truth |
| `/document` | Generates or updates `DESIGN.md` capturing the visual system tokens |
| `/shape` | Plans UX layout, data hierarchy, and responsive flow before writing code |
| `/critique` | Evaluates UX: hierarchy, clarity, contrast, and cognitive load |
| `/audit` | Runs technical checks: WCAG accessibility, touch targets, contrast ratios, performance |
| `/polish` | Final quality pass: aligns spacing rhythm, borders, hover states, and typography |
| `/bolder` | Elevates timid or bland layouts with punchy typography, deliberate color, and strong anchors |
| `/quieter` | Tones down over-stimulating, cluttered, or aggressive interfaces |
| `/distill` | Strips redundant UI clutter, removes nested cards, and emphasizes primary user actions |
| `/harden` | Adds error boundaries, empty states, text truncation, and internationalization resilience |
| `/animate` | Introduces purposeful micro-interactions with smooth ease-out curves (150-250ms) |
| `/colorize` | Applies purposeful color accents based on domain intent (telecom cyan, emerald health) |
| `/typeset` | Fixes font pairings, line heights, letter tracking, and tabular figures for numbers |
| `/layout` | Fixes monotonous grids and establishes clear visual cadence across breakpoints |
| `/delight` | Adds delightful touches (e.g. interactive sliders, live speed tests, playful copy) |

## Deterministic Anti-Patterns to Eliminate

1. **AI Palette Tells**: Never use generic purple-to-blue gradients (`from-indigo-500` or `from-purple-600 to-blue-500`). Use intentional, branded palettes (e.g., Telecom Cyan `#06b6d4`, Deep Slate `#0a0d14`).
2. **Nested Card Syndrome**: Never nest a bordered Card inside another bordered Card. Use subtle borders, whitespace, or flat dividers.
3. **Low-Contrast Grays**: Never put plain gray `#888` text on colored or tinted backgrounds. Match the text tint to the background with proper contrast.
4. **Pure Black & Pure White**: Avoid harsh `#000000` or `#ffffff` contrast in dark mode. Always tint backgrounds with cool slate or navy tones.
5. **Overused System Fonts**: Avoid generic Arial/Inter defaults when character is needed. Pair geometric sans display headers with crisp readable body fonts.
6. **Bouncy Transitions**: Avoid elastic or bounce easing. Always use `ease-out` or standard cubic-bezier curves for UI reliability.

## Project Context Files
- Check `PRODUCT.md` for target audience, brand lane, and constraints.
- Check `DESIGN.md` for color tokens, typography, and component styling rules.
- Test frontend components with `npx impeccable detect <file-path>` to catch anti-patterns.
