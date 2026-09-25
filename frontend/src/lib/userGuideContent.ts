// User Guide content for the Space Weather Dashboard.
//
// This is static, human-readable documentation of HOW TO USE the dashboard:
// every page, its controls and workflows, plus the domain concepts needed to
// read the data. It complements `referenceContent.ts` (which documents the
// underlying science). Kept as typed data so it renders instantly / offline and
// is easy to extend. Rendered by `app/user-guide/UserGuideClient.tsx`.
//
// The content-block model (para / list / formula / table) and the external-link
// shape are reused from the Science Reference page so both docs render
// identically.

import type { ReferenceBlock, ReferenceLink } from "@/lib/referenceContent";

export type GuideCategory =
  | "getting-started"
  | "monitoring"
  | "radio"
  | "analysis"
  | "events"
  | "settings"
  | "concepts";

/** An internal deep-link to the dashboard page an entry describes. */
export interface GuideLink {
  label: string;
  href: string;
}

export interface GuideEntry {
  /** Stable slug used for anchors, search and React keys. */
  id: string;
  title: string;
  category: GuideCategory;
  /** One-line summary shown on the collapsed accordion header. */
  short: string;
  /** Short topical tags shown as chips and matched in search. */
  tags?: string[];
  /** Detailed how-to body, reusing the Reference block model. */
  body: ReferenceBlock[];
  /** Internal link to the actual page this entry documents. */
  link?: GuideLink;
  /** External references (e.g. NOAA, SunPy docs). */
  references?: ReferenceLink[];
}

export interface GuideCategoryMeta {
  id: GuideCategory;
  label: string;
  blurb: string;
}

export const GUIDE_CATEGORIES: GuideCategoryMeta[] = [
  {
    id: "getting-started",
    label: "Getting Started",
    blurb:
      "How the dashboard is laid out, how to move around it, and the interface conventions that apply on every page.",
  },
  {
    id: "monitoring",
    label: "Real-Time Monitoring",
    blurb:
      "The live pages that chart the current state of the Sun, the solar wind and Earth's geomagnetic field.",
  },
  {
    id: "radio",
    label: "Solar Radio & Burst Tools",
    blurb:
      "e-CALLISTO radio spectrograms: live monitoring, ML burst detection and the interactive FITS analyzer.",
  },
  {
    id: "analysis",
    label: "Imaging & Analysis",
    blurb:
      "SunPy-powered SDO/AIA tools for plotting, difference imaging, compositing, active-region detection and movies.",
  },
  {
    id: "events",
    label: "Events, Forecast & Archive",
    blurb:
      "Looking ahead (forecasts), looking across time (timeline), staying informed (alerts) and looking back (archive).",
  },
  {
    id: "settings",
    label: "Settings & Reference",
    blurb:
      "Personalize appearance and notifications, and find the scientific reference behind the data.",
  },
  {
    id: "concepts",
    label: "Key Concepts",
    blurb:
      "The space-weather terms you need to interpret the numbers: flare classes, indices, solar-wind fields and forecast scales.",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Getting Started
// ─────────────────────────────────────────────────────────────────────────────

const GETTING_STARTED: GuideEntry[] = [
  {
    id: "layout-navigation",
    title: "Layout & Navigation",
    category: "getting-started",
    short:
      "Find your way around: the left sidebar lists every page, the header shows context, and the main area holds the content.",
    tags: ["sidebar", "navigation", "layout"],
    body: [
      {
        kind: "para",
        text:
          "The dashboard is organized into a fixed left sidebar and a main content area. The sidebar lists all pages grouped roughly by theme: real-time monitoring at the top, then radio and analysis tools, then forecasting, timeline and archive, and finally the reference, this guide, and settings at the bottom. The page you are currently on is highlighted in blue.",
      },
      {
        kind: "list",
        items: [
          "Click any sidebar item to jump straight to that page; navigation is instant (no full reload).",
          "The SWDash logo sits at the top of the sidebar; the app name and version sit at the bottom.",
          "Below the navigation, a \"Quick Look\" strip shows a handful of live headline values (see the Quick Look entry).",
          "Use the menu button in the header to collapse or expand the sidebar and reclaim screen width.",
        ],
      },
    ],
  },
  {
    id: "header-bar",
    title: "The Header Bar",
    category: "getting-started",
    short:
      "Every page has a header showing the page title, a sidebar toggle, the live UTC clock and the unread-alerts badge.",
    tags: ["header", "UTC", "clock"],
    body: [
      {
        kind: "para",
        text:
          "The header sits above the content on every page. On the left is a menu button that collapses/expands the sidebar and the current page title. On the right you'll find the live clock and quick access to alerts.",
      },
      {
        kind: "list",
        items: [
          "Live UTC time: all timestamps across the dashboard are in UTC (Coordinated Universal Time), the standard for space-weather data. There is no local-time conversion, so a time shown here matches what you'll see on NOAA and other sources.",
          "Alerts badge: a red counter appears when there are unread space-weather alerts; click it to open the Alerts page.",
        ],
      },
    ],
    link: { label: "Open Alerts", href: "/events" },
  },
  {
    id: "quick-look",
    title: "The Quick Look Strip",
    category: "getting-started",
    short:
      "A compact live summary in the sidebar (sunspot number, solar-wind speed and IMF Bz/Bt), refreshed every minute.",
    tags: ["sidebar", "summary", "live"],
    body: [
      {
        kind: "para",
        text:
          "Near the bottom of the sidebar, the \"Quick Look\" panel shows a few headline values so you can gauge conditions from any page without navigating away: the current sunspot number, solar-wind speed, and the IMF Bz and Bt components. A \"Last Updated\" time (UTC) shows how fresh the snapshot is; it auto-refreshes about once a minute.",
      },
      {
        kind: "para",
        text:
          "A blank value (shown as a dash) means it is temporarily unavailable from the upstream feed. See the Key Concepts section to interpret each value.",
      },
    ],
  },
  {
    id: "ui-conventions",
    title: "Common Interface Patterns",
    category: "getting-started",
    short:
      "Conventions that repeat across pages: UTC date pickers, range caps, auto-refresh, shareable URLs and export buttons.",
    tags: ["dates", "export", "refresh", "URL"],
    body: [
      {
        kind: "para",
        text:
          "Once you learn a few patterns, every page feels familiar. They apply consistently across the dashboard:",
      },
      {
        kind: "list",
        items: [
          "Dates and times are UTC. Date pickers default to a sensible value (often yesterday, since some datasets lag by a day).",
          "Range caps: detailed time-series pages (X-ray & Proton, Geomagnetic) accept a limited window (typically up to 7 days) so charts stay responsive.",
          "Auto-refresh: live charts update themselves in the background (using stale-while-revalidate), so you rarely need to reload. Switching browser tabs pauses updates until you return.",
          "Shareable / deep-link URLs: several tools encode their state in the address bar (e.g. ?date=YYYY-MM-DD, ?session=…). Copy the URL to return to the exact same view or share it.",
          "Exports: where data can be downloaded you'll see buttons for PNG (the rendered chart/image), CSV (the raw numbers), or FITS (raw scientific image data). Downloads use your browser's normal save dialog.",
        ],
      },
    ],
  },
  {
    id: "theme",
    title: "Light & Dark Theme",
    category: "getting-started",
    short:
      "The dashboard ships in dark mode but you can switch to light or follow your operating system, from Settings.",
    tags: ["theme", "dark mode", "appearance"],
    body: [
      {
        kind: "para",
        text:
          "The interface defaults to a dark theme suited to dim control-room / observatory environments. From the Settings page you can choose Light, Dark, or System (which follows your operating system's preference). Your choice is saved in the browser and persists between visits.",
      },
    ],
    link: { label: "Open Settings", href: "/settings" },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Real-Time Monitoring
// ─────────────────────────────────────────────────────────────────────────────

const MONITORING: GuideEntry[] = [
  {
    id: "overview",
    title: "Overview (Home)",
    category: "monitoring",
    short:
      "The landing page: a single-screen situational summary that stitches together every major data stream.",
    tags: ["overview", "home", "dashboard"],
    body: [
      {
        kind: "para",
        text:
          "The Overview is the front door to the dashboard: an at-a-glance status board of current space weather. It is assembled from summary cards and compact versions of the charts found on the dedicated pages. Read it top-to-bottom to build a full picture, then click through to a dedicated page for detail and controls.",
      },
      {
        kind: "list",
        items: [
          "Summary metric cards (top): current X-ray flare class, solar-wind speed, Kp, Dst, sunspot number, proton flux, IMF Bz/Bt and the count of active alerts.",
          "Forecast strip: predicted Kp for the next few hours, inbound CMEs, and the NOAA 3-day R/S/G outlook.",
          "Live charts: an e-CALLISTO radio dynamic spectrum, GOES X-ray flux, and GOES proton flux.",
          "Geomagnetic & imagery: Dst and Kp for the current day, a short SOHO/LASCO coronagraph clip, and a grid of the latest full-disk solar images, alongside a scrollable feed of the newest alerts.",
          "Solar wind & particles: solar-wind speed and IMF (Bt/Bz), plus GOES electron flux and magnetometer components.",
          "Solar indices: the F10.7 cm radio flux and the sunspot-number progression.",
        ],
      },
      {
        kind: "para",
        text:
          "Every panel here has a fuller counterpart elsewhere in the sidebar; use the Overview to spot what's interesting, then drill in.",
      },
    ],
    link: { label: "Open Overview", href: "/" },
  },
  {
    id: "xray-proton",
    title: "X-ray & Proton Flux",
    category: "monitoring",
    short:
      "GOES soft X-ray and energetic-proton time series with a date-range picker and CSV/PNG export.",
    tags: ["X-ray", "proton", "flares", "GOES"],
    body: [
      {
        kind: "para",
        text:
          "This page plots two GOES data streams that together characterize a solar flare and any radiation storm that follows it: the soft X-ray flux (which defines the flare class) and the integral proton flux at several energies.",
      },
      {
        kind: "list",
        items: [
          "Pick a date range (up to about 7 days) to load the series. The latest values are shown alongside the charts.",
          "The X-ray chart is logarithmic with the A/B/C/M/X flare-class bands marked, and shows both GOES channels (short 0.05 to 0.4 nm and long 0.1 to 0.8 nm).",
          "The proton chart stacks the >10, >50 and >100 MeV integral channels: the >10 MeV channel drives the NOAA S (radiation-storm) scale.",
          "Export the exact window you're viewing as CSV (numbers) or PNG (rendered plot) using the buttons on each chart.",
        ],
      },
      {
        kind: "para",
        text:
          "See the Key Concepts section for how to read flare classes and proton-storm levels.",
      },
    ],
    link: { label: "Open X-ray & Proton", href: "/xray-proton" },
  },
  {
    id: "solar-wind",
    title: "Solar Wind & IMF",
    category: "monitoring",
    short:
      "Near-real-time L1 solar-wind speed and interplanetary magnetic field (Bz/Bt) with a 2-hour to 7-day range selector.",
    tags: ["solar wind", "IMF", "Bz", "L1"],
    body: [
      {
        kind: "para",
        text:
          "This page tracks the stream of plasma and magnetic field arriving from the Sun, measured near the L1 point about 1.5 million km upstream of Earth: the earliest in-situ warning of changing conditions.",
      },
      {
        kind: "list",
        items: [
          "Use the range selector (2-hour, 6-hour, 1-day, 3-day, 7-day) to zoom the time window.",
          "The speed chart shows bulk solar-wind speed in km/s; the IMF chart shows Bt (total field strength) and Bz (the north-south component).",
          "A \"Live L1\" badge indicates the feed is the real-time (roughly 1-minute cadence) propagated solar-wind product.",
        ],
      },
      {
        kind: "para",
        text:
          "Why it matters: a strongly southward Bz (large negative value) is the single best precursor of geomagnetic storms. This is live monitoring data, so there is no export here.",
      },
    ],
    link: { label: "Open Solar Wind", href: "/solar-wind" },
  },
  {
    id: "geomagnetic",
    title: "Geomagnetic Indices",
    category: "monitoring",
    short:
      "The Kp and Dst indices, the standard measures of geomagnetic-storm intensity, with date-range search and export.",
    tags: ["Kp", "Dst", "geomagnetic", "storm"],
    body: [
      {
        kind: "para",
        text:
          "This page charts Earth's geomagnetic response to solar-wind driving via two complementary indices.",
      },
      {
        kind: "list",
        items: [
          "Choose a from/to date range to load the series.",
          "Kp (0 to 9, every 3 hours) is a planetary disturbance level; its bands map to the NOAA G-storm scale.",
          "Dst (in nanoteslas, hourly) tracks the equatorial ring current: deep negative values mark the main phase of a magnetic storm.",
          "A legend explains the Kp bands and Dst thresholds; where applicable, provisional vs. final values are flagged.",
          "Export either index over your chosen window as CSV or PNG.",
        ],
      },
    ],
    link: { label: "Open Geomagnetic", href: "/geomagnetic" },
  },
  {
    id: "solar-images",
    title: "Solar Images",
    category: "monitoring",
    short:
      "A grid of the latest full-disk solar images from SDO/AIA, SDO/HMI and GOES/SUVI, filterable by instrument.",
    tags: ["SDO", "AIA", "HMI", "SUVI", "imagery"],
    body: [
      {
        kind: "para",
        text:
          "A quick visual check of the Sun's current appearance across several instruments and wavelengths.",
      },
      {
        kind: "list",
        items: [
          "Filter the grid by instrument: All, SDO/AIA (extreme-UV), SDO/HMI (magnetogram/continuum) or GOES/SUVI (EUV).",
          "Each thumbnail is labeled with instrument, wavelength (for AIA) and the acquisition time (UTC).",
          "The grid auto-refreshes about every 5 minutes as new frames arrive.",
          "Click a thumbnail to open the full-resolution full-disk image.",
        ],
      },
    ],
    link: { label: "Open Solar Images", href: "/solar-images" },
  },
  {
    id: "coronagraph",
    title: "SOHO/LASCO Coronagraph",
    category: "monitoring",
    short:
      "LASCO C2/C3 white-light coronagraph movies plus a list of recent CMEs with WSA-ENLIL arrival predictions.",
    tags: ["LASCO", "coronagraph", "CME", "SOHO"],
    body: [
      {
        kind: "para",
        text:
          "The coronagraph blocks out the Sun's bright disk so the faint outer corona, and any coronal mass ejections (CMEs) leaving it, becomes visible.",
      },
      {
        kind: "list",
        items: [
          "Watch the LASCO C2 (inner) and C3 (outer) white-light movies to see CMEs propagate outward.",
          "A CME list gives each event's launch time, source location, speed and, where modeled, a WSA-ENLIL prediction of Earth-arrival time and expected impact.",
        ],
      },
    ],
    link: { label: "Open Coronagraph", href: "/coronagraph" },
  },
  {
    id: "solar-cycle",
    title: "Solar Cycle Progression",
    category: "monitoring",
    short:
      "The long-term view: monthly sunspot number and F10.7 flux against the official Solar Cycle 25 prediction.",
    tags: ["solar cycle", "sunspot", "F10.7", "Cycle 25"],
    body: [
      {
        kind: "para",
        text:
          "Where the monitoring pages show today, this page shows the years-long rhythm of the Sun's ~11-year activity cycle.",
      },
      {
        kind: "list",
        items: [
          "The main chart plots the observed monthly sunspot number with its 13-month smoothed curve, overlaid on NOAA's official Cycle 25 prediction and its uncertainty band.",
          "The F10.7 cm radio-flux series provides a complementary activity proxy.",
          "Use it to judge whether current activity is running above or below the predicted cycle.",
        ],
      },
    ],
    link: { label: "Open Solar Cycle", href: "/solar-cycle" },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Solar Radio & Burst Tools
// ─────────────────────────────────────────────────────────────────────────────

const RADIO: GuideEntry[] = [
  {
    id: "solar-radio",
    title: "Solar Radio (e-CALLISTO)",
    category: "radio",
    short:
      "Live e-CALLISTO dynamic spectra (Sri Lanka prioritized) with a slider through the day's detected burst events.",
    tags: ["e-CALLISTO", "radio", "dynamic spectrum"],
    body: [
      {
        kind: "para",
        text:
          "e-CALLISTO is a worldwide network of low-cost radio spectrometers that records the Sun's radio emission as a dynamic spectrum: a frequency-vs-time image where bursts appear as bright drifting features. This page surfaces the live feed (Sri Lanka station prioritized) and the day's burst events.",
      },
      {
        kind: "list",
        items: [
          "The live dynamic spectrum updates as new 15-minute segments are recorded.",
          "Use the burst-event slider to step through events detected during the day and inspect each one's spectrum.",
        ],
      },
      {
        kind: "para",
        text:
          "See the Key Concepts section for the radio burst types (II, III, IV, V) and how to read a dynamic spectrum.",
      },
    ],
    link: { label: "Open Solar Radio", href: "/solar-radio" },
  },
  {
    id: "burst-detector",
    title: "Burst Detector",
    category: "radio",
    short:
      "Run a burst classifier over a day of e-CALLISTO data, optionally label burst types, then review, corroborate and export what it found.",
    tags: ["burst", "ML", "detection", "e-CALLISTO", "CCM", "CCMT", "burst type"],
    body: [
      {
        kind: "para",
        text:
          "The Burst Detector runs a machine-learning classifier over e-CALLISTO recordings to find solar radio bursts automatically. Scanning happens as a background job you start and then monitor.",
      },
      {
        kind: "list",
        items: [
          "Pick a date (defaults to yesterday) and, optionally, which stations to include.",
          "Pick a Model: CCM v1.1.0 (default, newer, decision threshold 0.51) or CCM v1.0.0 (the original, threshold 0.595). A model shown as unavailable means its checkpoint has not been fetched — run 'git lfs pull'.",
          "Tick 'Classify burst types' to also label each burst as Type II, Type III or Other using CCMT v1.0.0. This adds a second pass, so runs take longer.",
          "Click Predict bursts to submit the job; the page polls its progress and shows results when finished.",
          "After a scan, toggle between two views without re-scanning: Criteria mode (default) keeps only detections that meet alert criteria (fewer, higher-confidence bursts), while Raw mode lists every segment the model flagged. Changing the model or the type toggle does require a new run, because those change the scores.",
          "Each detected segment shows its probability (color-coded by confidence), any burst type, and a dynamic-spectrum preview; segments seen by multiple stations are highlighted.",
          "The Official e-CALLISTO Burst List panel cross-checks detections against the published daily list.",
          "Export Events downloads the day's events as a .txt report, stamped with the model that produced them.",
        ],
      },
      {
        kind: "para",
        text:
          "How to read burst types: they are estimates, not measurements. The burst has to be found first by the binary model, then bright regions inside the segment are cropped and classified. If no region is large enough to classify reliably, the segment stays a burst with no type rather than being given a guess — 'mixed' on an event means its stations disagreed. Type III is the most reliable class; Other is the weakest. When the type matters, confirm it against the official burst list or in the e-CALLISTO Analyzer.",
      },
      {
        kind: "para",
        text:
          "Tip: opening this page with a ?date=YYYY-MM-DD in the URL (for example from an alert link) pre-fills that date and shows the stored real-time detections for it. Those come from the background scan, which uses whichever model the server is configured with.",
      },
    ],
    link: { label: "Open Burst Detector", href: "/burst-predictor" },
  },
  {
    id: "ecallisto-analyzer",
    title: "e-CALLISTO Analyzer",
    category: "radio",
    short:
      "An interactive FITS viewer for radio spectrograms: background subtraction, colormaps, RFI filtering, stats and export.",
    tags: ["FITS", "analyzer", "RFI", "spectrogram"],
    body: [
      {
        kind: "para",
        text:
          "The Analyzer is a hands-on workbench for individual e-CALLISTO FITS files. Load a spectrogram, tune how it's processed and displayed, inspect statistics, and export the result. You can keep several files open as separate sessions (tabs) and switch between them.",
      },
      {
        kind: "list",
        items: [
          "Load data by dragging in a FITS file (.fit / .fits / .fit.gz), using the file picker, or browsing the archive by date, station and filename.",
          "Aggregation method: choose how the quiet-Sun background is estimated and subtracted (median, mean or RMS).",
          "Intensity unit: display power as dB, linear or square-root.",
          "Time unit: label the time axis as UTC, HH:MM:SS or relative seconds from the start.",
          "Colormap: pick a color scheme (magma, viridis, plasma, inferno, …).",
          "Vmin/Vmax: set the display range manually or let it auto-scale from the data statistics.",
          "RFI filtering: toggle radio-frequency-interference suppression and set low/high percentile excluders to drop noisy channels.",
        ],
      },
      {
        kind: "list",
        items: [
          "A statistics panel reports min/max/mean intensity, the frequency range (MHz) and the time span.",
          "Export the current view as PNG or the processed data as FITS.",
          "Save your session and render settings as a project (JSON) and reload it later.",
        ],
      },
      {
        kind: "para",
        text:
          "Controls are debounced, so the preview updates a moment after you stop adjusting a slider rather than on every pixel of movement.",
      },
    ],
    link: { label: "Open e-CALLISTO Analyzer", href: "/e-callisto-analyzer" },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Imaging & Analysis
// ─────────────────────────────────────────────────────────────────────────────

const ANALYSIS: GuideEntry[] = [
  {
    id: "data-analysis-sources",
    title: "Data Analysis: Loading Data",
    category: "analysis",
    short:
      "Four ways to bring SDO/AIA (and HMI) frames into the analysis workbench: upload, Fido fetch, JSOC archive or a sequence.",
    tags: ["SunPy", "SDO", "AIA", "data source"],
    body: [
      {
        kind: "para",
        text:
          "The Data Analysis page is a SunPy-powered workbench for solar imagery. Before you can analyze anything you need to load one or more frames, and there are four sources to choose from.",
      },
      {
        kind: "list",
        items: [
          "Upload FITS: drop in your own frames (up to about 60) for a time series.",
          "Fetch via Fido: pull near-real-time or historical frames from the archives. This runs as a background job and can be slow.",
          "JSOC Archive: a fast path to a single synoptic frame; prefer this over Fido when you just need a recent image.",
          "Archive Sequence: build a multi-frame time series from the archive (background job), the basis for difference imaging and movies.",
        ],
      },
      {
        kind: "para",
        text:
          "Tip: Fido fetches can take a while, so when you only need a quick look the JSOC/Archive paths are much faster. Loading opens a session; its id is stored in the URL (?session=…) so you can return to it.",
      },
    ],
    link: { label: "Open Data Analysis", href: "/data-analysis" },
  },
  {
    id: "data-analysis-plot",
    title: "Data Analysis: Plot",
    category: "analysis",
    short:
      "Render a single frame with full control over color scale, clipping, cropping and scientific overlays.",
    tags: ["plot", "colormap", "crop", "overlay"],
    body: [
      {
        kind: "para",
        text:
          "The Plot tool renders one frame as a publication-style image. It's the default view and the basis for the other tools.",
      },
      {
        kind: "list",
        items: [
          "Colormap & scale: choose a color scheme and an intensity scaling (linear, log, sqrt or power-law) to bring out faint or bright structure.",
          "Clipping: set low/high percentiles (roughly 1 to 99.9%) to reject outliers and improve contrast.",
          "Vmin/Vmax: fix the display range manually or auto-scale it.",
          "Cropping: enter bottom-left and top-right pixel coordinates to zoom into a region of interest.",
          "Overlays: toggle the solar limb (circle), a latitude/longitude grid, and a colorbar.",
          "Download the rendered frame as PNG or the processed data as (compressed) FITS.",
        ],
      },
    ],
    link: { label: "Open Data Analysis", href: "/data-analysis" },
  },
  {
    id: "data-analysis-difference",
    title: "Data Analysis: Difference Imaging",
    category: "analysis",
    short:
      "Subtract frames to reveal change: running difference (frame minus previous) or base difference (minus a reference).",
    tags: ["difference", "running", "base", "change"],
    body: [
      {
        kind: "para",
        text:
          "Difference imaging cancels the static Sun so that moving fronts (EUV waves, dimmings, erupting material) stand out. It needs a multi-frame session.",
      },
      {
        kind: "list",
        items: [
          "Running difference: each frame minus the one before it, ideal for tracking propagating disturbances.",
          "Base difference: each frame minus a chosen reference frame, ideal for showing cumulative change from a starting point.",
          "Toggling between the two is instant because differences are pre-computed on the server.",
        ],
      },
    ],
    link: { label: "Open Data Analysis", href: "/data-analysis" },
  },
  {
    id: "data-analysis-composite",
    title: "Data Analysis: Composite & Active Regions",
    category: "analysis",
    short:
      "Overlay HMI magnetic contours on an AIA image, or detect active regions via the HEK catalog or an intensity threshold.",
    tags: ["composite", "HMI", "active regions", "HEK"],
    body: [
      {
        kind: "para",
        text:
          "Two related tools tie the emission you see to the magnetic field that drives it.",
      },
      {
        kind: "list",
        items: [
          "Composite: overlay an HMI line-of-sight magnetogram (as contours) on an AIA EUV image to see how bright emission relates to magnetic polarity. Adjust the contour level (roughly ±100 to ±2400 gauss).",
          "Active Regions: highlight active regions either from the NOAA/HEK catalog (HEK method) or by an intensity-percentile threshold you set (roughly 95 to 100%). Detected regions are drawn as color-coded contours.",
        ],
      },
    ],
    link: { label: "Open Data Analysis", href: "/data-analysis" },
  },
  {
    id: "data-analysis-movie",
    title: "Data Analysis: Movies & Frame Controls",
    category: "analysis",
    short:
      "Turn a multi-frame session into an MP4 or GIF, and scrub between frames with the slider or keyboard.",
    tags: ["movie", "MP4", "GIF", "frames"],
    body: [
      {
        kind: "para",
        text:
          "Once you have a sequence loaded you can animate it and navigate it frame-by-frame.",
      },
      {
        kind: "list",
        items: [
          "Movie: build an MP4 (H.264) or animated GIF as a background job. Set the frame rate (roughly 1 to 30 fps) and choose whether to render plain Plot frames (with your current settings) or running-Difference frames. When the job finishes, download the result.",
          "Frame controls: move through frames with the slider or the left/right arrow keys, auto-play the sequence, and pick the base frame used by the difference and composite tools.",
        ],
      },
    ],
    link: { label: "Open Data Analysis", href: "/data-analysis" },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Events, Forecast & Archive
// ─────────────────────────────────────────────────────────────────────────────

const EVENTS: GuideEntry[] = [
  {
    id: "forecast",
    title: "Forecast & Prediction",
    category: "events",
    short:
      "Look ahead: predicted Kp, incoming CMEs with arrival estimates, the NOAA R/S/G outlook and the aurora forecast.",
    tags: ["forecast", "Kp", "CME", "aurora", "NOAA scales"],
    body: [
      {
        kind: "para",
        text:
          "This page gathers the dashboard's forward-looking products into one place.",
      },
      {
        kind: "list",
        items: [
          "Predicted Kp: a short-term Kp estimate derived from solar-wind coupling (the Newell dΦ/dt coupling function), mapped to the NOAA G-scale.",
          "CME list: recent and imminent CMEs from NOAA's DONKI catalog: start time, source location, speed, cone width, type, whether it's Earth-directed, and (when modeled) a WSA-ENLIL predicted arrival time and impact Kp, with a link to DONKI.",
          "NOAA Scales: the R (radio blackout), S (radiation storm) and G (geomagnetic storm) scales for yesterday, today-so-far and the 3-day forecast.",
          "Aurora forecast: OVATION hemispheric power and rendered aurora-oval maps for the north and south poles.",
        ],
      },
    ],
    link: { label: "Open Forecast", href: "/forecast" },
  },
  {
    id: "timeline",
    title: "Event Timeline",
    category: "events",
    short:
      "A combined, time-aligned feed of radio bursts, X-ray flares, proton events, CMEs and geomagnetic storms.",
    tags: ["timeline", "events", "history"],
    body: [
      {
        kind: "para",
        text:
          "The Timeline lays every event type on shared, time-aligned lanes so you can see how they relate: for example an X-ray flare, then a radio burst, then a CME, then a geomagnetic storm days later.",
      },
      {
        kind: "list",
        items: [
          "Lanes include official and ML-detected radio bursts, GOES X-ray flares, proton events, DONKI CMEs and geomagnetic storms.",
          "Choose a date range (effectively unbounded) to load events.",
          "Hover an event for a tooltip with its full metadata; click it to open the alert detail and, where relevant, deep-link to the Archive or Burst Detector.",
          "Export the selected events as CSV.",
        ],
      },
    ],
    link: { label: "Open Timeline", href: "/timeline" },
  },
  {
    id: "alerts",
    title: "Alerts",
    category: "events",
    short:
      "The running list of active space-weather alerts, with an unread badge and deep-links to the relevant page.",
    tags: ["alerts", "notifications", "events"],
    body: [
      {
        kind: "para",
        text:
          "The Alerts page lists current space-weather alerts and events. The sidebar and header show an unread count so you notice new ones from anywhere.",
      },
      {
        kind: "list",
        items: [
          "Read an alert to clear it from the unread count.",
          "Click an alert to jump to the page that gives it context: the Archive, Burst Detector or Timeline.",
          "Configure how you're notified from the Settings page (see Notifications).",
        ],
      },
    ],
    link: { label: "Open Alerts", href: "/events" },
  },
  {
    id: "archive",
    title: "Archive",
    category: "events",
    short:
      "Search historical data across instruments (radio bursts, solar images, X-ray/proton and geomagnetic) by date.",
    tags: ["archive", "history", "search", "download"],
    body: [
      {
        kind: "para",
        text:
          "The Archive is the dashboard's back-catalog: a tabbed search over past data by instrument and date.",
      },
      {
        kind: "list",
        items: [
          "Radio Bursts (e-CALLISTO): pick a station and date (a ★ marks stations with metadata), then step through 15-minute segments with the prev/next navigator. The dynamic spectrum is on the left and the burst list on the right, with per-burst details. Download the processed spectrum as PNG or the raw data as FITS; a summary shows total and Sri-Lanka-only burst counts.",
          "Solar Images: browse archived full-disk imagery by date.",
          "X-ray / Proton: load GOES flux for a chosen date and export it.",
          "Geomagnetic: load Kp and Dst over a from/to date range.",
        ],
      },
    ],
    link: { label: "Open Archive", href: "/archive" },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Settings & Reference
// ─────────────────────────────────────────────────────────────────────────────

const SETTINGS: GuideEntry[] = [
  {
    id: "settings",
    title: "Settings",
    category: "settings",
    short:
      "Personalize the dashboard: choose a theme, pick the automatic burst-detection model, check burst-detection coverage and fill in days missed while offline, and configure how you receive alert notifications.",
    tags: ["settings", "theme", "notifications", "model", "burst detection", "coverage", "backfill", "catch-up", "offline"],
    body: [
      {
        kind: "para",
        text:
          "The Settings page holds your preferences — some personal to this browser, some shared by everyone using this dashboard.",
      },
      {
        kind: "list",
        items: [
          "Appearance: switch the theme between Light, Dark and System; your choice is remembered in this browser.",
          "Automatic Burst Detection: choose which classifier — CCM v1.1.0 or CCM v1.0.0 — the background scan runs over new e-CALLISTO data to raise radio-burst alerts. This is a server-side setting, so it applies to every viewer and survives a restart. The change takes effect on the next scan, which re-scores the last few hours with the new model and rebuilds the burst alerts from it, and each model alerts on its own tuned probability threshold. The Burst Detector page's per-run model picker is unaffected — it simply starts from this choice.",
          "Detection Coverage: burst detection only runs on live data, so any time the dashboard is offline leaves gaps in the burst timeline and the activity histograms. The backend re-scores missed days automatically in the background — the strip shows one cell per day (green = fully scored, amber = still incomplete) and the run's progress. Today is always amber: its most recent hours belong to the live scan. You can start a run yourself, stop one, or aim it at an older date range than the automatic window covers. Filled-in bursts appear everywhere the live ones do but never send notifications, so closing an old gap does not replay stale alerts.",
          "Notifications: manage alert-notification preferences and send a test notification to confirm delivery works.",
        ],
      },
    ],
    link: { label: "Open Settings", href: "/settings" },
  },
  {
    id: "science-reference",
    title: "Science Reference",
    category: "settings",
    short:
      "A companion, searchable encyclopedia of the instruments, parameters and methods behind the data.",
    tags: ["reference", "science", "glossary"],
    body: [
      {
        kind: "para",
        text:
          "This User Guide explains how to operate the dashboard. Its companion, the Science Reference page, explains the science: the instruments that make the measurements, the parameters and indices used to describe solar activity, and the methods that turn raw data into the products you see. It works the same way as this guide (search and expand entries), so use it whenever you want the physics behind a number.",
      },
    ],
    link: { label: "Open Science Reference", href: "/reference" },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Key Concepts
// ─────────────────────────────────────────────────────────────────────────────

const CONCEPTS: GuideEntry[] = [
  {
    id: "flare-class",
    title: "Solar Flare Classes (A to X)",
    category: "concepts",
    short:
      "Flares are graded by peak soft X-ray flux on a logarithmic A/B/C/M/X scale, each letter ten times the last.",
    tags: ["flare", "X-ray", "class"],
    body: [
      {
        kind: "para",
        text:
          "A solar flare's strength is its peak brightness in the GOES 0.1 to 0.8 nm soft X-ray channel. The scale is logarithmic: each letter is ten times more intense than the one below it, and the number after the letter is a linear multiplier (so X2 is twice X1, and M9 is just below X1).",
      },
      {
        kind: "table",
        caption: "Flare class vs. peak 1 to 8 Å X-ray flux (W/m²)",
        columns: ["Class", "Peak flux (W/m²)", "Typical effect"],
        rows: [
          ["A", "< 1e-7", "Background; negligible"],
          ["B", "1e-7 to 1e-6", "Minor; usually no impact"],
          ["C", "1e-6 to 1e-5", "Small; minor/none at Earth"],
          ["M", "1e-5 to 1e-4", "Medium; brief radio blackouts (R1 to R2)"],
          ["X", "≥ 1e-4", "Large; strong blackouts, possible storms (R3+)"],
        ],
      },
      {
        kind: "para",
        text:
          "You'll see flare classes on the Overview, X-ray & Proton and Timeline pages.",
      },
    ],
  },
  {
    id: "radio-burst-types",
    title: "Radio Burst Types & Dynamic Spectra",
    category: "concepts",
    short:
      "A dynamic spectrum plots radio intensity over frequency and time; burst types II to V have distinct signatures.",
    tags: ["radio", "burst", "Type II", "Type III"],
    body: [
      {
        kind: "para",
        text:
          "A dynamic spectrum is a frequency-vs-time image of the Sun's radio emission; brighter pixels mean stronger emission. Because higher frequencies come from denser, lower parts of the corona, features that drift from high to low frequency trace disturbances moving outward from the Sun. The main solar burst types:",
      },
      {
        kind: "list",
        items: [
          "Type II: slow frequency drift over minutes; signals a shock wave, often from a CME, and can precede a proton event.",
          "Type III: very fast drift, appearing almost vertical; marks beams of electrons escaping along open field lines. Often occurs in groups.",
          "Type IV: broadband emission lasting minutes to hours after a strong flare, from trapped electrons in moving or stationary structures.",
          "Type V: short, smooth continuum sometimes following Type III bursts.",
        ],
      },
      {
        kind: "para",
        text:
          "Explore these on the Solar Radio, Burst Detector and e-CALLISTO Analyzer pages.",
      },
    ],
  },
  {
    id: "kp-dst",
    title: "Geomagnetic Indices: Kp & Dst",
    category: "concepts",
    short:
      "Kp (0 to 9) is a global 3-hour disturbance level; Dst (nT) measures the storm-time ring current at the equator.",
    tags: ["Kp", "Dst", "storm", "G-scale"],
    body: [
      {
        kind: "list",
        items: [
          "Kp: a quasi-logarithmic 0 to 9 index derived from mid-latitude magnetometers every 3 hours. Kp ≥ 5 is storm level and maps to the NOAA G1 to G5 scale (G1 = Kp 5, up to G5 = Kp 9).",
          "Dst: the Disturbance Storm Time index (in nanoteslas, hourly). It measures the ring current: quiet is near 0; the more negative it goes, the stronger the storm (e.g. below −100 nT is an intense storm). Recovery takes hours to days.",
        ],
      },
      {
        kind: "para",
        text:
          "Both are charted on the Geomagnetic page and summarized on the Overview.",
      },
    ],
  },
  {
    id: "solar-wind-imf",
    title: "Solar Wind Speed, Bz & Bt",
    category: "concepts",
    short:
      "The solar wind's speed and its embedded magnetic field (Bt total, Bz north/south) determine how it drives storms.",
    tags: ["solar wind", "Bz", "Bt", "IMF"],
    body: [
      {
        kind: "list",
        items: [
          "Speed: bulk flow speed of the solar wind, roughly 300 to 400 km/s when quiet, and 800+ km/s in fast streams or CME-driven flows.",
          "Bt: the total strength of the interplanetary magnetic field (IMF) carried by the wind, in nanoteslas. Larger Bt means more energy is available to couple into the magnetosphere.",
          "Bz: the north-south component of the IMF. A southward (negative) Bz reconnects with Earth's field and is the key ingredient for geomagnetic storms; a northward (positive) Bz largely shuts the coupling off.",
        ],
      },
      {
        kind: "para",
        text:
          "These are measured near the L1 point about 1.5 million km sunward of Earth, giving roughly 15 to 60 minutes of warning before the wind reaches us. See the Solar Wind & IMF page.",
      },
    ],
  },
  {
    id: "cme",
    title: "CMEs & Arrival Prediction",
    category: "concepts",
    short:
      "A coronal mass ejection is a large eruption of plasma and magnetic field; WSA-ENLIL models its Earth arrival.",
    tags: ["CME", "ENLIL", "coronagraph"],
    body: [
      {
        kind: "para",
        text:
          "A coronal mass ejection (CME) is a billion-tonne eruption of magnetized plasma from the corona. Earth-directed CMEs are the primary cause of major geomagnetic storms. Coronagraphs (SOHO/LASCO) catch them leaving the Sun; the WSA-ENLIL model then propagates them through the solar wind to predict when, and how hard, they will strike Earth.",
      },
      {
        kind: "para",
        text:
          "See the Coronagraph and Forecast pages for CME imagery, catalogs and arrival predictions.",
      },
    ],
  },
  {
    id: "noaa-scales",
    title: "NOAA Space Weather Scales (R / S / G)",
    category: "concepts",
    short:
      "NOAA grades three hazards on 1 to 5 scales: R (radio blackouts), S (radiation storms) and G (geomagnetic storms).",
    tags: ["NOAA", "R-scale", "S-scale", "G-scale"],
    body: [
      {
        kind: "table",
        caption: "The three NOAA scales and what drives them",
        columns: ["Scale", "Hazard", "Driven by"],
        rows: [
          ["R1 to R5", "Radio blackouts", "Solar flare soft X-ray flux (M/X class)"],
          ["S1 to S5", "Solar radiation storms", ">10 MeV proton flux (pfu)"],
          ["G1 to G5", "Geomagnetic storms", "Kp index / geomagnetic disturbance"],
        ],
      },
      {
        kind: "para",
        text:
          "Each scale runs from 1 (minor) to 5 (extreme). The Forecast page shows observed and predicted R/S/G levels; the Overview shows the 3-day outlook.",
      },
    ],
  },
  {
    id: "sunspot-f107",
    title: "Sunspot Number & F10.7 Flux",
    category: "concepts",
    short:
      "Two long-term activity proxies: the sunspot number counts spots; F10.7 measures 10.7 cm solar radio emission.",
    tags: ["sunspot", "F10.7", "solar cycle"],
    body: [
      {
        kind: "list",
        items: [
          "Sunspot number: a count of dark, magnetically intense spots on the photosphere. It rises and falls over the ~11-year solar cycle and is usually shown as a 13-month smoothed curve for the cycle view.",
          "F10.7: the solar radio flux at 10.7 cm wavelength (in solar flux units). It tracks the same activity as sunspots but is measured objectively from the ground every day, and correlates with the Sun's EUV/X-ray output.",
        ],
      },
      {
        kind: "para",
        text:
          "Both appear on the Overview and Solar Cycle pages.",
      },
    ],
  },
  {
    id: "l1-lead-time",
    title: "L1 & Warning Lead Time",
    category: "concepts",
    short:
      "The L1 Lagrange point, ~1.5 million km sunward, hosts the monitors that give Earth its solar-wind early warning.",
    tags: ["L1", "lead time", "monitoring"],
    body: [
      {
        kind: "para",
        text:
          "L1 is the Sun-Earth Lagrange point about 1.5 million km upstream of Earth, where spacecraft can hover and sample the solar wind before it reaches us. Because the wind takes roughly 15 to 60 minutes to travel from L1 to Earth (depending on its speed), in-situ measurements there (speed, density and the IMF including Bz) provide the primary short-fuse warning of incoming geomagnetic activity.",
      },
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Aggregate + search helper
// ─────────────────────────────────────────────────────────────────────────────

export const GUIDE_ENTRIES: GuideEntry[] = [
  ...GETTING_STARTED,
  ...MONITORING,
  ...RADIO,
  ...ANALYSIS,
  ...EVENTS,
  ...SETTINGS,
  ...CONCEPTS,
];

/** Build the lowercased search haystack for one entry (title, summary, tags, body, link). */
export function entrySearchText(entry: GuideEntry): string {
  const parts: string[] = [entry.title, entry.short, ...(entry.tags ?? [])];
  for (const block of entry.body) {
    if (block.kind === "para") parts.push(block.text);
    else if (block.kind === "list") parts.push(...block.items);
    else if (block.kind === "formula") parts.push(block.expr, block.note ?? "");
    else if (block.kind === "table") {
      if (block.caption) parts.push(block.caption);
      parts.push(...block.columns, ...block.rows.flat());
    }
  }
  if (entry.link) parts.push(entry.link.label);
  return parts.join(" ").toLowerCase();
}
