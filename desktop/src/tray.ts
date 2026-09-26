import { app, Menu, nativeImage, shell, Tray } from "electron";

<<<<<<< HEAD
import { openEnvFile } from "./envfile";
import { assetPath, HOME, LOG_DIR } from "./paths";
=======
import { setStartAtLogin, startsAtLogin } from "./autostart";
import { openEnvFile } from "./envfile";
import { APP_ICON, HOME, LOG_DIR } from "./paths";
>>>>>>> d325f0ffea140b14d8efde51c7c0cf3c0712f39b
import { saveState, state } from "./state";

export interface TrayActions {
  open: () => void;
  restartBackend: () => void;
  checkForUpdates: () => void;
  quit: () => void;
}

<<<<<<< HEAD
// Launched at login with this flag: start the backend, stay in the tray.
export const HIDDEN_FLAG = "--hidden";

function startsWithWindows(): boolean {
  return app.getLoginItemSettings({ args: [HIDDEN_FLAG] }).openAtLogin;
}

export function createTray(actions: TrayActions): Tray {
  const tray = new Tray(nativeImage.createFromPath(assetPath("icon.ico")));
=======
export function createTray(actions: TrayActions): Tray {
  let icon = nativeImage.createFromPath(APP_ICON);
  // The Linux icon is the 512 px PNG; tray hosts expect something panel-sized.
  if (process.platform === "linux") icon = icon.resize({ width: 32, height: 32, quality: "best" });
  const tray = new Tray(icon);
>>>>>>> d325f0ffea140b14d8efde51c7c0cf3c0712f39b
  tray.setToolTip("Solar Monitoring Dashboard");

  const rebuild = (): void => {
    tray.setContextMenu(
      Menu.buildFromTemplate([
        { label: "Open Dashboard", click: actions.open },
        { type: "separator" },
        {
          label: "Desktop notifications",
          type: "checkbox",
          checked: state.notifications,
          click: (item) => {
            state.notifications = item.checked;
            saveState();
          },
        },
        {
<<<<<<< HEAD
          label: "Start with Windows",
          type: "checkbox",
          // A dev build would register electron.exe itself at login.
          enabled: app.isPackaged,
          checked: app.isPackaged && startsWithWindows(),
          click: (item) => {
            app.setLoginItemSettings({ openAtLogin: item.checked, args: [HIDDEN_FLAG] });
=======
          label: process.platform === "win32" ? "Start with Windows" : "Start at login",
          type: "checkbox",
          // A dev build would register electron.exe itself at login.
          enabled: app.isPackaged,
          checked: app.isPackaged && startsAtLogin(),
          click: (item) => {
            setStartAtLogin(item.checked);
>>>>>>> d325f0ffea140b14d8efde51c7c0cf3c0712f39b
            rebuild();
          },
        },
        { type: "separator" },
        { label: "Open data folder", click: () => void shell.openPath(HOME) },
        { label: "Edit settings (.env)…", click: openEnvFile },
        { label: "Open logs", click: () => void shell.openPath(LOG_DIR) },
        { label: "Restart backend", click: actions.restartBackend },
        { label: "Check for updates…", click: actions.checkForUpdates },
        { type: "separator" },
        { label: "Quit", click: actions.quit },
      ]),
    );
  };

  rebuild();
  tray.on("click", actions.open);
  return tray;
}
