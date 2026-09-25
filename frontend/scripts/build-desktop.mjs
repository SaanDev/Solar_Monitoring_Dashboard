// Static export for the Windows desktop app: `npm run build:desktop` -> out/.
// Sets the two build flags (see next.config.mjs and src/lib/api.ts) and runs
// `next build`; a script rather than inline `VAR=x` so it works the same in
// PowerShell, cmd and CI.
//
// Like `next build`, this writes .next/ — don't run it while `next dev` is
// serving from this same folder.
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const nextBin = require.resolve("next/dist/bin/next");

const result = spawnSync(process.execPath, [nextBin, "build"], {
  stdio: "inherit",
  env: { ...process.env, NEXT_OUTPUT: "export", NEXT_PUBLIC_DESKTOP: "1" },
});
process.exit(result.status ?? 1);
