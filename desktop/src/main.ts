import { app, BrowserWindow, dialog, Menu, shell, Tray } from "electron";
import log from "electron-log/main";
import * as path from "node:path";

import { startAlertPolling } from "./alerts";
import { Backend, choosePort } from "./backend";
import { openEnvFile } from "./envfile";
import { assetPath, ensureDir, HOME, LOG_DIR } from "./paths";
import { saveState, state } from "./state";
import { createTray, HIDDEN_FLAG } from "./tray";
import { checkForUpdatesInteractive, initUpdater } from "./updater";

const APP_ID = "org.saandev.solardashboard"; // = appId in electron-builder.yml
const BACKGROUND = "#0f1117"; // the dashboard's dark surface, so nothing flashes white

// Keep Chromium's profile (localStorage, cache) with the rest of the user's data,
// so "reset the app" is deleting one folder. Must precede the single-instance
// lock, which lives in userData.
ensureDir(HOME);
app.setPath("userData", path.join(HOME, "electron"));
log.transports.file.resolvePathFn = () => path.join(LOG_DIR, "main.log");
log.errorHandler.startCatching();
// The AppUserModelID is the app's identity on Windows: toasts are attributed to
// it, and the taskbar takes its icon from the Start Menu shortcut carrying it.
// Electron writes such a shortcut (named after the running exe) for toast
// activation, so a dev run (`npm start`, i.e. electron.exe) must not use the real
// id — it would leave an "Electron" shortcut claiming it, and the installed app's
// taskbar button would then show the Electron logo.
app.setAppUserModelId(app.isPackaged ? APP_ID : `${APP_ID}.dev`);

let backend: Backend | null = null;
let win: BrowserWindow | null = null;
let splash: BrowserWindow | null = null;
let tray: Tray | null = null;
let quitting = false;
let errorDialogOpen = false;

function isAppUrl(url: string): boolean {
  try {
    return backend !== null && new URL(url).origin === backend.origin;
  } catch {
    return false;
  }
}

function openExternal(url: string): void {
  try {
    if (["http:", "https:", "mailto:"].includes(new URL(url).protocol)) void shell.openExternal(url);
  } catch {
    // not a URL
  }
}

function createSplash(): BrowserWindow {
  const s = new BrowserWindow({
    width: 440,
    height: 300,
    frame: false,
    resizable: false,
    show: false,
    backgroundColor: BACKGROUND,
    icon: assetPath("icon.ico"),
    webPreferences: { sandbox: true, contextIsolation: true },
  });
  s.once("ready-to-show", () => s.show());
  void s.loadFile(assetPath("splash.html"));
  return s;
}

function closeSplash(): void {
  splash?.destroy();
  splash = null;
}

function createMainWindow(origin: string, pathname = "/"): BrowserWindow {
  const w = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    title: "Solar Monitoring Dashboard",
    backgroundColor: BACKGROUND,
    icon: assetPath("icon.ico"),
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  w.on("page-title-updated", (e) => e.preventDefault());

  // The UI only ever talks to its own backend; anything else is a link the
  // user clicked (data sources, docs) and belongs in their browser.
  w.webContents.setWindowOpenHandler(({ url }) => {
    if (isAppUrl(url)) return { action: "allow" };
    openExternal(url);
    return { action: "deny" };
  });
  w.webContents.on("will-navigate", (e, url) => {
    if (!isAppUrl(url)) {
      e.preventDefault();
      openExternal(url);
    }
  });

  // Closing hides to the tray: collection and alerts keep running.
  w.on("close", (e) => {
    if (quitting) return;
    e.preventDefault();
    w.hide();
    if (!state.trayHintShown && tray) {
      tray.displayBalloon({
        iconType: "info",
        title: "Still running in the tray",
        content: "Data collection and alerts continue. Right-click the tray icon to quit.",
      });
      state.trayHintShown = true;
      saveState();
    }
  });
  w.on("closed", () => {
    win = null;
  });

  w.once("ready-to-show", () => {
    w.show();
    closeSplash();
  });
  void w.loadURL(`${origin}${pathname}`);
  return w;
}

function showWindow(pathname?: string): void {
  if (!backend) return;
  if (!win) {
    win = createMainWindow(backend.origin, pathname);
    return;
  }
  if (pathname) void win.loadURL(`${backend.origin}${pathname}`);
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

async function showBackendError(detail: string): Promise<void> {
  if (errorDialogOpen || quitting) return;
  errorDialogOpen = true;
  closeSplash();
  const { response } = await dialog.showMessageBox({
    type: "error",
    title: "Solar Monitoring Dashboard",
    message: "The dashboard's backend isn't running.",
    detail: `${detail}\n\nLogs: ${LOG_DIR}`,
    buttons: ["Try again", "Open logs", "Quit"],
    defaultId: 0,
    cancelId: 2,
  });
  errorDialogOpen = false;
  if (response === 0) void restartBackend();
  else if (response === 1) void shell.openPath(LOG_DIR);
  else app.quit();
}

async function restartBackend(): Promise<void> {
  if (!backend) return;
  try {
    await backend.restart();
    if (win) win.reload();
    else if (!process.argv.includes(HIDDEN_FLAG)) showWindow();
  } catch (err) {
    log.error("backend restart failed", err);
    await backend.stop();
    void showBackendError(backend.consoleTail());
  }
}

function buildAppMenu(): Menu {
  return Menu.buildFromTemplate([
    {
      label: "File",
      submenu: [
        { label: "Open data folder", click: () => void shell.openPath(HOME) },
        { label: "Edit settings (.env)…", click: openEnvFile },
        { label: "Open logs", click: () => void shell.openPath(LOG_DIR) },
        { type: "separator" },
        { label: "Quit", accelerator: "Ctrl+Q", click: () => app.quit() },
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    {
      label: "Help",
      submenu: [
        { label: "User guide", click: () => showWindow("/user-guide/") },
        { label: "Check for updates…", click: () => void checkForUpdatesInteractive() },
        { type: "separator" },
        { label: `Version ${app.getVersion()}`, enabled: false },
      ],
    },
  ]);
}

async function main(): Promise<void> {
  await app.whenReady();
  const startHidden = process.argv.includes(HIDDEN_FLAG);
  Menu.setApplicationMenu(buildAppMenu());

  tray = createTray({
    open: () => showWindow(),
    restartBackend: () => void restartBackend(),
    checkForUpdates: () => void checkForUpdatesInteractive(),
    quit: () => app.quit(),
  });
  if (!startHidden) splash = createSplash();

  backend = new Backend(await choosePort());
  backend.on("failed", (tail: string) => void showBackendError(tail));
  backend.on("recovered", () => win?.reload());
  backend.start();
  try {
    await backend.waitReady();
  } catch (err) {
    log.error("backend failed to start", err);
    await backend.stop(); // cancels the automatic restart; the dialog offers one
    void showBackendError(backend.consoleTail());
    return;
  }
  log.info(`backend ready at ${backend.origin}`);

  startAlertPolling(backend.origin, (pathname) => showWindow(pathname));
  initUpdater(async () => {
    quitting = true;
    await backend?.stop();
  });
  if (!startHidden) showWindow();
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => showWindow());
  // The window hides rather than closes, and the splash may close before it
  // exists; never let "no windows" end the app — only Quit does.
  app.on("window-all-closed", () => undefined);
  app.on("before-quit", (e) => {
    quitting = true;
    if (backend?.running) {
      // Stop the backend first so its shutdown runs (and, on update, so the
      // installer can replace the bundled python.exe), then quit for real.
      e.preventDefault();
      void backend.stop().finally(() => app.quit());
    }
  });
  main().catch((err) => {
    log.error("startup failed", err);
    dialog.showErrorBox("Solar Monitoring Dashboard", String(err instanceof Error ? err.stack : err));
    app.quit();
  });
}
