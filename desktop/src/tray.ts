import { app, Menu, nativeImage, shell, Tray } from "electron";

import { setStartAtLogin, startsAtLogin } from "./autostart";
import { openEnvFile } from "./envfile";
import { APP_ICON, HOME, LOG_DIR } from "./paths";
import { saveState, state } from "./state";

export interface TrayActions {
  open: () => void;
  restartBackend: () => void;
  checkForUpdates: () => void;
  quit: () => void;
}

export function createTray(actions: TrayActions): Tray {
  let icon = nativeImage.createFromPath(APP_ICON);
  // The Linux icon is the 512 px PNG; tray hosts expect something panel-sized.
  if (process.platform === "linux") icon = icon.resize({ width: 32, height: 32, quality: "best" });
  const tray = new Tray(icon);
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
          label: process.platform === "win32" ? "Start with Windows" : "Start at login",
          type: "checkbox",
          // A dev build would register electron.exe itself at login.
          enabled: app.isPackaged,
          checked: app.isPackaged && startsAtLogin(),
          click: (item) => {
            setStartAtLogin(item.checked);
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
