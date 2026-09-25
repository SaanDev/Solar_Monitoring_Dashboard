import { ChildProcess, spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import * as fs from "node:fs";
import * as net from "node:net";
import * as path from "node:path";
import log from "electron-log/main";

import { HOME, LOG_DIR, ensureDir, runtimePaths } from "./paths";

/** Fixed so the page origin — and with it localStorage (theme, UI prefs) — is
 * the same on every launch. Must match DEFAULT_PORT in backend/app/desktop.py. */
export const PREFERRED_PORT = 47800;

// First launch creates the schema and warms the ML models; allow for a slow disk.
const READY_TIMEOUT_MS = 180_000;
const STOP_GRACE_MS = 10_000;
const RESTART_DELAYS_MS = [2_000, 5_000, 10_000];
const RESTART_WINDOW_MS = 10 * 60_000;
const CONSOLE_LOG = path.join(LOG_DIR, "backend-console.log");

function listenOn(port: number): Promise<number | null> {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once("error", () => resolve(null));
    srv.listen(port, "127.0.0.1", () => {
      const bound = (srv.address() as net.AddressInfo).port;
      srv.close(() => resolve(bound));
    });
  });
}

/** PREFERRED_PORT when free, otherwise any free port (this session then gets a
 * different origin, so browser-stored UI settings don't carry over). */
export async function choosePort(): Promise<number> {
  const preferred = await listenOn(PREFERRED_PORT);
  if (preferred !== null) return preferred;
  const fallback = await listenOn(0);
  if (fallback === null) throw new Error("no free local port for the backend");
  log.warn(`port ${PREFERRED_PORT} is in use; backend will use ${fallback} this session`);
  return fallback;
}

/**
 * Runs `python -m app.desktop` (FastAPI + scheduler + ML, one process) and keeps
 * it alive.
 *
 * Events: "recovered" after an automatic restart is serving again; "failed"
 * (with the tail of the console log) once restarts are exhausted.
 */
export class Backend extends EventEmitter {
  private child: ChildProcess | null = null;
  private stopping = false;
  private restartTimes: number[] = [];

  constructor(readonly port: number) {
    super();
  }

  get origin(): string {
    return `http://127.0.0.1:${this.port}`;
  }

  get running(): boolean {
    const c = this.child;
    // No pid means the spawn itself failed (e.g. python.exe missing).
    return c !== null && c.pid !== undefined && c.exitCode === null && c.signalCode === null;
  }

  start(): void {
    const rt = runtimePaths();
    ensureDir(LOG_DIR);
    // Per launch: only has to explain a failed start (Python warnings and up);
    // backend.log has the full, rotated history.
    const out = fs.openSync(CONSOLE_LOG, "w");

    const env: NodeJS.ProcessEnv = { ...process.env };
    // A user's own Python setup must not leak into the bundled interpreter.
    for (const key of ["PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV", "CONDA_PREFIX"]) delete env[key];
    Object.assign(env, {
      PYTHONPATH: rt.backendDir,
      PYTHONNOUSERSITE: "1",
      PYTHONDONTWRITEBYTECODE: "1",
      PYTHONUTF8: "1",
      SWD_HOME: HOME,
      SWD_PORT: String(this.port),
      SWD_FRONTEND_DIR: rt.frontendDir,
      SWD_LIFELINE: "stdin",
    });

    log.info(`starting backend: ${rt.python} -P -m app.desktop (port ${this.port})`);
    this.stopping = false;
    // -P: don't put the working directory on sys.path; `app` comes from PYTHONPATH.
    const child = spawn(rt.python, ["-P", "-m", "app.desktop"], {
      cwd: HOME,
      env,
      stdio: ["pipe", out, out],
      windowsHide: true,
    });
    fs.closeSync(out);
    // Writing "quit" to an already-dead child raises EPIPE on the stream.
    child.stdin?.on("error", () => undefined);
    child.on("error", (err) => {
      log.error("could not start backend", err);
      this.emit("failed", `${err.message}\n\nPython: ${rt.python}`);
    });
    child.on("exit", (code, signal) => this.onExit(child, code, signal));
    this.child = child;
  }

  /** Resolves once /api/status answers; rejects if the process dies first. */
  async waitReady(timeoutMs = READY_TIMEOUT_MS): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (!this.running) throw new Error("backend exited during startup");
      try {
        const res = await fetch(`${this.origin}/api/status`, { signal: AbortSignal.timeout(2_000) });
        if (res.ok) return;
      } catch {
        // not listening yet
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    throw new Error(`backend did not become ready within ${timeoutMs / 1000}s`);
  }

  /** Graceful stop: "quit" on the lifeline lets the app's lifespan shut the
   * scheduler down; kill only if it hasn't exited within the grace period. */
  stop(): Promise<void> {
    const child = this.child;
    this.stopping = true;
    if (!child || !this.running) return Promise.resolve();
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        log.warn("backend did not exit in time; killing it");
        child.kill();
      }, STOP_GRACE_MS);
      child.once("exit", () => {
        clearTimeout(timer);
        resolve();
      });
      child.stdin?.write("quit\n");
      child.stdin?.end();
    });
  }

  async restart(): Promise<void> {
    await this.stop();
    this.restartTimes = [];
    this.start();
    await this.waitReady();
  }

  consoleTail(maxChars = 3000): string {
    try {
      const text = fs.readFileSync(CONSOLE_LOG, "utf8");
      return text.slice(-maxChars).trim() || "(no output)";
    } catch {
      return "(no console log)";
    }
  }

  private onExit(child: ChildProcess, code: number | null, signal: NodeJS.Signals | null): void {
    if (child !== this.child) return; // an older process from before a restart
    if (this.stopping) {
      log.info("backend stopped");
      return;
    }
    log.error(`backend exited unexpectedly (code ${code}, signal ${signal})`);
    const now = Date.now();
    this.restartTimes = this.restartTimes.filter((t) => now - t < RESTART_WINDOW_MS);
    const attempt = this.restartTimes.length;
    if (attempt >= RESTART_DELAYS_MS.length) {
      this.emit("failed", this.consoleTail());
      return;
    }
    this.restartTimes.push(now);
    const delay = RESTART_DELAYS_MS[attempt];
    log.info(`restarting backend in ${delay / 1000}s (attempt ${attempt + 1})`);
    setTimeout(() => {
      if (this.stopping) return;
      this.start();
      this.waitReady().then(
        () => this.emit("recovered"),
        (err) => log.error("backend restart failed", err),
      );
    }, delay);
  }
}
