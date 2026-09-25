import { app, Menu, nativeImage, shell, Tray } from "electron";

import { openEnvFile } from "./envfile";
import { assetPath, HOME, LOG_DIR } from "./paths";
import { saveState, state } from "./state";

export interface TrayActions {
  open: () => void;
  restartBackend: () => void;
  checkForUpdates: () => void;
  quit: () => void;
}

// Launched at login with this flag: start the backend, stay in the tray.
export const HIDDEN_FLAG = "--hidden";

function startsWithWindows(): boolean {
  return app.getLoginItemSettings({ args: [HIDDEN_FLAG] }).openAtLogin;
}

export function createTray(actions: TrayActions): Tray {
  const tray = new Tray(nativeImage.createFromPath(assetPath("icon.ico")));
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
          label: "Start with Windows",
          type: "checkbox",
          // A dev build would register electron.exe itself at login.
          enabled: app.isPackaged,
          checked: app.isPackaged && startsWithWindows(),
          click: (item) => {
            app.setLoginItemSettings({ openAtLogin: item.checked, args: [HIDDEN_FLAG] });
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
