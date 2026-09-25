import { app } from "electron";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

/** Per-user data root: SQLite DB, downloaded data, logs, user `.env`.
 * LOCALAPPDATA, not the roaming profile — this grows to gigabytes.
 * Must match the default in backend/app/desktop.py. */
export const HOME = path.join(
  process.env.LOCALAPPDATA ?? path.join(os.homedir(), "AppData", "Local"),
  "SolarDashboard",
);
export const LOG_DIR = path.join(HOME, "logs");
export const ENV_FILE = path.join(HOME, ".env");
export const STATE_FILE = path.join(HOME, "desktop-state.json");

export interface RuntimePaths {
  python: string;
  backendDir: string;
  frontendDir: string;
}

/** Where the Python runtime, backend source and static UI live.
 *
 * Packaged: bundled under resources/ by electron-builder (extraResources).
 * Dev (`npm start`): the repo checkout — the backend venv and the static export
 * from `npm --prefix ../frontend run build:desktop`. SWD_PYTHON /
 * SWD_BACKEND_DIR / SWD_FRONTEND_DIR override either. */
export function runtimePaths(): RuntimePaths {
  const repo = path.resolve(__dirname, "..", "..");
  const base = app.isPackaged
    ? {
        python: path.join(process.resourcesPath, "python", "python.exe"),
        backendDir: path.join(process.resourcesPath, "backend"),
        frontendDir: path.join(process.resourcesPath, "frontend"),
      }
    : {
        python: path.join(repo, "backend", ".venv", "Scripts", "python.exe"),
        backendDir: path.join(repo, "backend"),
        frontendDir: path.join(repo, "frontend", "out"),
      };
  return {
    python: process.env.SWD_PYTHON ?? base.python,
    backendDir: process.env.SWD_BACKEND_DIR ?? base.backendDir,
    frontendDir: process.env.SWD_FRONTEND_DIR ?? base.frontendDir,
  };
}

export function ensureDir(dir: string): void {
  fs.mkdirSync(dir, { recursive: true });
}

/** Files shipped in desktop/assets (inside app.asar when packaged). */
export function assetPath(name: string): string {
  return path.join(__dirname, "..", "assets", name);
}
