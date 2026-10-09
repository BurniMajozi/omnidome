// Bundles tests/deck-studio.test.ts with esbuild and runs it under node:test.
// Usage (from apps/web): node scripts/test-deck-studio.mjs
import { build } from "esbuild"
import { spawnSync } from "node:child_process"
import { fileURLToPath } from "node:url"
import path from "node:path"

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const out = path.join(root, ".deck-studio-test.tmp.mjs")
await build({
  entryPoints: [path.join(root, "tests/deck-studio.test.ts")],
  bundle: true,
  platform: "node",
  format: "esm",
  outfile: out,
  packages: "external",
  tsconfig: path.join(root, "tsconfig.json"),
  logLevel: "error",
})
const r = spawnSync(process.execPath, ["--test", out], { stdio: "inherit", cwd: root })
process.exit(r.status ?? 1)
