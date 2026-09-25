import { app, dialog } from "electron";
import log from "electron-log/main";
import { autoUpdater } from "electron-updater";

const CHECK_EVERY_MS = 6 * 60 * 60_000;
const IS_LINUX = process.platform === "linux";

/**
 * Auto-update from GitHub Releases (the `publish` block in
 * electron-builder.yml). Updates download in the background.
 *
 * Windows: installing needs the backend stopped first, because the installer
 * replaces the bundled python.exe and its DLLs, which are locked while it runs.
 *
 * Linux (.deb): electron-updater installs the package with `pkexec dpkg -i`,
 * which asks for the user's password, so it only happens when they choose
 * "Restart now" (never silently on quit). dpkg can replace files that are in
 * use, so the app keeps running until the install has succeeded; a cancelled
 * or failed install leaves it exactly as it was.
 */
export function initUpdater(prepareQuit: () => Promise<void>): void {
  if (!app.isPackaged) return;
  autoUpdater.logger = log;
  autoUpdater.autoDownload = true;
  // Windows: otherwise installed on the next normal quit (which also stops the backend).
  autoUpdater.autoInstallOnAppQuit = !IS_LINUX;

  autoUpdater.on("update-downloaded", async (info) => {
    const { response } = await dialog.showMessageBox({
      type: "info",
      title: "Update ready",
      message: `Solar Monitoring Dashboard ${info.version} has been downloaded.`,
      detail: IS_LINUX
        ? "Restart now to install it (you'll be asked for your password), or later from Help → Check for updates."
        : "Restart now to install it, or it will be installed the next time you quit the app.",
      buttons: ["Restart now", "Later"],
      defaultId: 0,
      cancelId: 1,
    });
    if (response !== 0) return;
    if (IS_LINUX) {
      installOnLinux();
      return;
    }
    await prepareQuit();
    autoUpdater.quitAndInstall();
  });

  const check = (): void => {
    autoUpdater.checkForUpdates().catch((err) => log.warn("update check failed", err));
  };
  setTimeout(check, 15_000);
  setInterval(check, CHECK_EVERY_MS);
}

/** Installs the downloaded .deb, then quits (stopping the backend as on any
 * quit) and relaunches. quitAndInstall runs the install synchronously and
 * reports a failure, such as a cancelled password prompt, as an "error" event
 * before returning. */
function installOnLinux(): void {
  const errors: Error[] = [];
  const onError = (err: Error): void => void errors.push(err);
  autoUpdater.on("error", onError);
  try {
    autoUpdater.quitAndInstall(false, true);
  } finally {
    autoUpdater.off("error", onError);
  }
  if (errors.length === 0) return;
  void dialog.showMessageBox({
    type: "warning",
    message: "The update wasn't installed.",
    detail:
      `${errors[0].message}\n\nThe dashboard keeps running on this version. Try again from ` +
      "Help → Check for updates, or install the .deb from the Releases page.",
  });
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
