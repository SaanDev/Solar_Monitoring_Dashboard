import { spawn } from "node:child_process";
import * as fs from "node:fs";

import { ENV_FILE, ensureDir, HOME } from "./paths";

// The backend runs with its working directory in HOME, so pydantic-settings
// reads this file; any setting from .env.example can go here.
const TEMPLATE = `# Solar Monitoring Dashboard - desktop settings
#
# Uncomment a line and set a value, then use "Restart backend" in the tray menu.
# Any setting from the project's .env.example works here. The database, data
# folder and port are managed by the app - don't set DATABASE_URL, REDIS_URL,
# DATA_DIR or CORS_ORIGINS.

# JSOC export e-mail: enables the fast SDO/AIA download path on Data Analysis.
# Register it first at http://jsoc.stanford.edu/ajax/register_email.html
# JSOC_EMAIL=you@example.com

# Telegram alert delivery (bot token from @BotFather; the chat id and the
# channels themselves are set on the dashboard's Settings page).
# TELEGRAM_BOT_TOKEN=

# Radio-burst detection, and how many days of downtime the catch-up refills.
# RADIO_BURST_ENABLED=true
# RADIO_BURST_BACKFILL_MAX_DAYS=30
`;

/** Open the user's .env in Notepad, creating it from the template first. */
export function openEnvFile(): void {
  ensureDir(HOME);
  if (!fs.existsSync(ENV_FILE)) fs.writeFileSync(ENV_FILE, TEMPLATE.replace(/\n/g, "\r\n"));
  spawn("notepad.exe", [ENV_FILE], { detached: true, stdio: "ignore" }).unref();
}
