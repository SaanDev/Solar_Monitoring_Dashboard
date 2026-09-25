import * as fs from "node:fs";
import log from "electron-log/main";

import { STATE_FILE } from "./paths";

/** Shell-only preferences, kept next to the rest of the user's data. */
export interface DesktopState {
  notifications: boolean;
  trayHintShown: boolean;
  seenAlertIds: string[];
}

const DEFAULTS: DesktopState = { notifications: true, trayHintShown: false, seenAlertIds: [] };

function load(): DesktopState {
  try {
    return { ...DEFAULTS, ...JSON.parse(fs.readFileSync(STATE_FILE, "utf8")) };
  } catch {
    return { ...DEFAULTS };
  }
}

export const state: DesktopState = load();

export function saveState(): void {
  try {
    const tmp = `${STATE_FILE}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(state, null, 2));
    fs.renameSync(tmp, STATE_FILE);
  } catch (err) {
    log.warn("could not save desktop state", err);
  }
}
