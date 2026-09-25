import { app, dialog } from "electron";
import log from "electron-log/main";
import { autoUpdater } from "electron-updater";

const CHECK_EVERY_MS = 6 * 60 * 60_000;

/**
 * Auto-update from GitHub Releases (the `publish` block in
 * electron-builder.yml). Updates download in the background; installing needs
 * the backend stopped first, because the installer replaces the bundled
 * python.exe and its DLLs, which are locked while it runs.
 */
export function initUpdater(prepareQuit: () => Promise<void>): void {
  if (!app.isPackaged) return;
  autoUpdater.logger = log;
  autoUpdater.autoDownload = true;
  // Otherwise installed on the next normal quit (which also stops the backend).
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on("update-downloaded", async (info) => {
    const { response } = await dialog.showMessageBox({
      type: "info",
      title: "Update ready",
      message: `Solar Monitoring Dashboard ${info.version} has been downloaded.`,
      detail: "Restart now to install it, or it will be installed the next time you quit the app.",
      buttons: ["Restart now", "Later"],
      defaultId: 0,
      cancelId: 1,
    });
    if (response === 0) {
      await prepareQuit();
      autoUpdater.quitAndInstall();
    }
  });

  const check = (): void => {
    autoUpdater.checkForUpdates().catch((err) => log.warn("update check failed", err));
  };
  setTimeout(check, 15_000);
  setInterval(check, CHECK_EVERY_MS);
}

/** "Check for updates…" from the tray/menu: same check, but with feedback. */
export async function checkForUpdatesInteractive(): Promise<void> {
  if (!app.isPackaged) {
    await dialog.showMessageBox({ type: "info", message: "Updates are only available in the installed app." });
    return;
  }
  try {
    const result = await autoUpdater.checkForUpdates();
    if (!result?.isUpdateAvailable) {
      await dialog.showMessageBox({
        type: "info",
        message: "You're up to date.",
        detail: `Version ${app.getVersion()} is the latest release.`,
      });
    } else {
      await dialog.showMessageBox({
        type: "info",
        message: `Version ${result.updateInfo.version} is downloading.`,
        detail: "You'll be asked to restart when it's ready.",
      });
    }
  } catch (err) {
    log.warn("manual update check failed", err);
    await dialog.showMessageBox({
      type: "warning",
      message: "Couldn't check for updates.",
      detail: String(err instanceof Error ? err.message : err),
    });
  }
}
