import { app } from "electron";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const IS_WINDOWS = process.platform === "win32";

/** Where per-user app data belongs on this platform. Windows: LOCALAPPDATA, not
 * the roaming profile — this grows to gigabytes. Linux: the XDG data dir
 * (~/.local/share unless XDG_DATA_HOME says otherwise; the spec ignores
 * relative values). */
function userDataRoot(): string {
  if (IS_WINDOWS) return process.env.LOCALAPPDATA ?? path.join(os.homedir(), "AppData", "Local");
  const xdg = process.env.XDG_DATA_HOME;
  return xdg && path.isAbsolute(xdg) ? xdg : path.join(os.homedir(), ".local", "share");
}

/** Per-user data root: SQLite DB, downloaded data, logs, user `.env`.
 * Must match the default in backend/app/desktop.py. */
export const HOME = path.join(userDataRoot(), "SolarDashboard");
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
        python: path.join(process.resourcesPath, "python", IS_WINDOWS ? "python.exe" : path.join("bin", "python3")),
        backendDir: path.join(process.resourcesPath, "backend"),
        frontendDir: path.join(process.resourcesPath, "frontend"),
      }
    : {
        python: IS_WINDOWS
          ? path.join(repo, "backend", ".venv", "Scripts", "python.exe")
          : path.join(repo, "backend", ".venv", "bin", "python"),
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

/** Window and tray icon: Windows wants the multi-size .ico, Linux a PNG. */
export const APP_ICON = assetPath(IS_WINDOWS ? "icon.ico" : "icon.png");
