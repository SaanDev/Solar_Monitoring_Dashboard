import { app } from "electron";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

// Launched at login with this flag: start the backend, stay in the tray.
export const HIDDEN_FLAG = "--hidden";

// Electron's login-item API covers Windows (and macOS) only; on Linux the
// freedesktop way is a .desktop file in ~/.config/autostart.
const IS_LINUX = process.platform === "linux";
const AUTOSTART_NAME = "solar-monitoring-dashboard.desktop"; // = desktopName in package.json

function autostartFile(): string {
  const xdg = process.env.XDG_CONFIG_HOME;
  const config = xdg && path.isAbsolute(xdg) ? xdg : path.join(os.homedir(), ".config");
  return path.join(config, "autostart", AUTOSTART_NAME);
}

/** One Exec= argument, quoted as the Desktop Entry spec requires (the install
 * path has spaces: /opt/Solar Monitoring Dashboard/...). */
function execArg(arg: string): string {
  if (!/[\s"'\\`$<>~|&;*?#()%]/.test(arg)) return arg;
  const quoted = `"${arg.replace(/["`$\\]/g, "\\$&")}"`;
  // Backslashes are escaped once more at the string level, and % is a field code.
  return quoted.replace(/\\/g, "\\\\").replace(/%/g, "%%");
}

export function startsAtLogin(): boolean {
  if (!IS_LINUX) return app.getLoginItemSettings({ args: [HIDDEN_FLAG] }).openAtLogin;
  return fs.existsSync(autostartFile());
}

export function setStartAtLogin(enabled: boolean): void {
  if (!IS_LINUX) {
    app.setLoginItemSettings({ openAtLogin: enabled, args: [HIDDEN_FLAG] });
    return;
  }
  const file = autostartFile();
  if (!enabled) {
    fs.rmSync(file, { force: true });
    return;
  }
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const entry = [
    "[Desktop Entry]",
    "Type=Application",
    "Name=Solar Monitoring Dashboard",
    "Comment=Keeps collecting space-weather data and raising alerts in the background",
    `Exec=${execArg(process.execPath)} ${HIDDEN_FLAG}`,
    "Icon=solar-monitoring-dashboard",
    "Terminal=false",
    "X-GNOME-Autostart-enabled=true",
    "",
  ];
  fs.writeFileSync(file, entry.join("\n"));
}
