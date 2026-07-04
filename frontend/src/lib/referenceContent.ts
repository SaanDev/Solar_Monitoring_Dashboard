// Scientific reference content for the Space Weather Dashboard.
//
// This is static, human-readable documentation of the instruments, physical
// parameters, and analysis methods surfaced across the dashboard. It is kept
// as typed data (rather than a backend feed) because it is reference text that
// changes rarely and should render instantly / offline. Rendered by
// `app/reference/ReferenceClient.tsx`.

export type ReferenceCategory = "instruments" | "parameters" | "methods";

/** A structured content block inside an entry's detailed body. */
export type ReferenceBlock =
  | { kind: "para"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "formula"; expr: string; note?: string }
  | { kind: "table"; caption?: string; columns: string[]; rows: string[][] };

export interface ReferenceLink {
  label: string;
  url: string;
}

export interface ReferenceEntry {
  /** Stable slug used for anchors, search and React keys. */
  id: string;
  title: string;
  category: ReferenceCategory;
  /** One-line summary shown on the collapsed accordion header. */
  short: string;
  /** Alternate names / abbreviations, included in search matching. */
  aka?: string[];
  /** Short topical tags shown as chips and matched in search. */
  tags?: string[];
  /** Detailed scientific description. */
  body: ReferenceBlock[];
  /** Where this dashboard actually pulls the data / imagery from. */
  dataSources?: string[];
  /** Dashboard pages where this instrument/parameter/method appears. */
  usedIn?: string[];
  references?: ReferenceLink[];
}

export interface ReferenceCategoryMeta {
  id: ReferenceCategory;
  label: string;
  blurb: string;
}

export const REFERENCE_CATEGORIES: ReferenceCategoryMeta[] = [
  {
    id: "instruments",
    label: "Instruments",
    blurb:
      "The spacecraft and ground-based observatories whose measurements and imagery feed the dashboard.",
  },
  {
    id: "parameters",
    label: "Parameters & Indices",
    blurb:
      "The physical quantities and standardized indices used to describe solar activity and its terrestrial impact.",
  },
  {
    id: "methods",
    label: "Methods & Products",
    blurb:
      "The processing, detection and forecasting techniques applied to the raw data before you see it.",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Instruments
// ─────────────────────────────────────────────────────────────────────────────

const INSTRUMENTS: ReferenceEntry[] = [
  {
    id: "goes-xrs",
    title: "GOES X-Ray Sensor (XRS)",
    category: "instruments",
    short:
      "Geostationary soft X-ray photometer measuring whole-Sun X-ray irradiance; the standard for solar flare classification.",
    aka: ["XRS", "EXIS", "GOES-16", "GOES-18", "GOES-19"],
    tags: ["X-ray", "flare", "GOES"],
    body: [
      {
        kind: "para",
        text:
          "The X-Ray Sensor is part of the EXIS instrument on NOAA's GOES-R series spacecraft (GOES-16/17/18/19), flown in geostationary orbit ~35,800 km above the equator. It measures the Sun's disk-integrated soft X-ray irradiance continuously, giving an uninterrupted record of solar flare activity independent of local time or weather.",
      },
      {
        kind: "para",
        text:
          "XRS observes two broadband channels: a short wavelength band at 0.05–0.4 nm (0.5–4 Å) and a long wavelength band at 0.1–0.8 nm (1–8 Å). The 1–8 Å channel's peak flux defines the internationally used flare class. Data are reported roughly every second and commonly averaged to 1-minute cadence.",
      },
      {
        kind: "para",
        text:
          "Because soft X-rays are absorbed high in Earth's dayside ionosphere (the D-region), a rising XRS flux is the earliest quantitative sign of a flare and directly predicts short-wave radio blackouts (the NOAA R-scale).",
      },
    ],
    dataSources: ["NOAA SWPC GOES XRS JSON feeds (primary GOES satellite)"],
    usedIn: ["Overview", "X-ray & Proton", "Archive", "Timeline"],
    references: [
      { label: "NOAA GOES-R EXIS", url: "https://www.goes-r.gov/spacesegment/exis.html" },
      { label: "SWPC GOES X-ray flux", url: "https://www.swpc.noaa.gov/products/goes-x-ray-flux" },
    ],
  },
  {
    id: "goes-seiss",
    title: "GOES Particle Sensors (SEISS / EPS)",
    category: "instruments",
    short:
      "Geostationary detectors counting energetic protons and electrons that quantify radiation storms and satellite-charging risk.",
    aka: ["SEISS", "SGPS", "MPS", "EPEAD", "particle detector"],
    tags: ["protons", "electrons", "radiation", "GOES"],
    body: [
      {
        kind: "para",
        text:
          "The Space Environment In-Situ Suite (SEISS) on GOES-R (and its EPEAD/MAGED heritage on older GOES) measures the flux of charged particles at geostationary altitude. Two populations matter most for space weather.",
      },
      {
        kind: "list",
        items: [
          "Solar energetic protons — integral flux above 10, 50 and 100 MeV, reported in proton flux units (pfu = particles cm⁻² s⁻¹ sr⁻¹). The >10 MeV channel defines the NOAA solar radiation storm (S) scale.",
          "Energetic electrons — the >2 MeV integral flux (e⁻ cm⁻² s⁻¹ sr⁻¹), which drives deep-dielectric (internal) charging of satellites when it stays elevated.",
        ],
      },
      {
        kind: "para",
        text:
          "Sitting outside most of the magnetosphere's shielding, GOES sees solar protons soon after they arrive along interplanetary field lines, so it provides the operational trigger for radiation-storm alerts affecting aviation, astronauts and spacecraft.",
      },
    ],
    dataSources: ["NOAA SWPC GOES integral proton & >2 MeV electron JSON feeds"],
    usedIn: ["Overview", "X-ray & Proton"],
    references: [
      { label: "NOAA GOES-R SEISS", url: "https://www.goes-r.gov/spacesegment/seiss.html" },
    ],
  },
  {
    id: "goes-magnetometer",
    title: "GOES Magnetometer",
    category: "instruments",
    short:
      "In-situ fluxgate magnetometer sampling Earth's field at geostationary orbit to reveal magnetospheric compression and substorms.",
    aka: ["MAG", "geostationary magnetometer"],
    tags: ["magnetic field", "magnetosphere", "GOES"],
    body: [
      {
        kind: "para",
        text:
          "Each GOES spacecraft carries a fluxgate magnetometer that measures the local geomagnetic field vector at ~6.6 Earth radii. Components are reported as Hp (parallel to the spin axis, roughly northward), He (earthward) and Hn (eastward), plus the total field.",
      },
      {
        kind: "para",
        text:
          "At geostationary orbit the field responds directly to solar-wind pressure and magnetospheric dynamics: sudden increases mark magnetopause compression from an arriving CME/shock, while sharp dips and rebounds signal substorm particle injections. It complements ground magnetometers by sensing the space side of the same disturbance.",
      },
    ],
    dataSources: ["NOAA SWPC GOES magnetometer JSON feed"],
    usedIn: ["Geomagnetic"],
    references: [
      { label: "NOAA GOES-R MAG", url: "https://www.goes-r.gov/spacesegment/mag.html" },
    ],
  },
  {
    id: "sdo-aia",
    title: "SDO — Atmospheric Imaging Assembly (AIA)",
    category: "instruments",
    short:
      "Full-disk EUV/UV imager on NASA's Solar Dynamics Observatory returning the corona in multiple temperature-sensitive channels every 12 seconds.",
    aka: ["AIA", "Solar Dynamics Observatory", "EUV imager"],
    tags: ["imaging", "EUV", "corona", "SDO"],
    body: [
      {
        kind: "para",
        text:
          "AIA is one of three instruments on NASA's Solar Dynamics Observatory (launched 2010, inclined geosynchronous orbit). Four telescopes feed 4096×4096 CCDs at ~0.6 arcsec per pixel, imaging the full solar disk with a nominal 12-second cadence.",
      },
      {
        kind: "para",
        text:
          "AIA captures seven narrow extreme-ultraviolet (EUV) passbands plus UV and visible channels. Each EUV band is dominated by emission lines from specific iron/helium ions, so a given wavelength maps to a characteristic plasma temperature — letting analysts isolate the cool chromosphere, quiet corona, active-region loops and multi-million-kelvin flare plasma. See the AIA passbands entry for the channel-to-temperature key.",
      },
      {
        kind: "para",
        text:
          "In this dashboard AIA imagery underpins the near-real-time Solar Images view and the SunPy-based Data Analysis tools (cropping, difference imaging, composites, movies).",
      },
    ],
    dataSources: [
      "Helioviewer / JSOC (near-real-time browse imagery)",
      "SunPy Fido + JSOC synoptic FITS (Data Analysis)",
    ],
    usedIn: ["Solar Images", "Data Analysis", "Archive"],
    references: [
      { label: "LMSAL — AIA", url: "https://aia.lmsal.com/" },
      { label: "SDO mission", url: "https://sdo.gsfc.nasa.gov/" },
    ],
  },
  {
    id: "sdo-hmi",
    title: "SDO — Helioseismic & Magnetic Imager (HMI)",
    category: "instruments",
    short:
      "Maps the Sun's photospheric magnetic field and surface motions; the source of the magnetograms overlaid in composite analyses.",
    aka: ["HMI", "magnetogram", "continuum"],
    tags: ["magnetic field", "photosphere", "SDO"],
    body: [
      {
        kind: "para",
        text:
          "HMI observes the photospheric absorption line of neutral iron (Fe I 6173 Å) across a 4096×4096 detector. From the line's polarization and Doppler shift it derives continuum intensity images, Dopplergrams (surface velocity) and line-of-sight and vector magnetograms of the surface magnetic field.",
      },
      {
        kind: "para",
        text:
          "Magnetograms reveal the polarity and strength of active-region magnetic fields — the ultimate energy source of flares and CMEs. In the Data Analysis composite tool, an HMI line-of-sight magnetogram is reprojected onto the AIA frame and drawn as ± polarity contours so coronal structures can be tied back to the photospheric field. HMI's Dopplergrams also enable helioseismology.",
      },
    ],
    dataSources: ["JSOC / SunPy Fido (HMI LOS magnetograms for composites)"],
    usedIn: ["Data Analysis", "Solar Images"],
    references: [{ label: "HMI (Stanford)", url: "http://hmi.stanford.edu/" }],
  },
  {
    id: "soho-lasco",
    title: "SOHO — LASCO Coronagraphs",
    category: "instruments",
    short:
      "White-light coronagraphs that occult the solar disk to image the faint outer corona and track coronal mass ejections.",
    aka: ["LASCO", "C2", "C3", "coronagraph", "SOHO"],
    tags: ["coronagraph", "CME", "corona", "SOHO"],
    body: [
      {
        kind: "para",
        text:
          "The Large Angle and Spectrometric Coronagraph (LASCO) flies on the ESA/NASA SOHO spacecraft near the Sun–Earth L1 point. An occulting disk blocks the blindingly bright photosphere so LASCO can image the million-times-fainter corona in visible light.",
      },
      {
        kind: "list",
        items: [
          "C2 — inner white-light coronagraph, field of view ~1.5–6 solar radii, best for the onset and inner structure of CMEs.",
          "C3 — outer coronagraph, ~3.7–30 solar radii, used to track CMEs outward and estimate plane-of-sky speed.",
        ],
      },
      {
        kind: "para",
        text:
          "Running-difference LASCO movies are the workhorse for spotting Earth-directed 'halo' CMEs. SOHO also carries EIT (EUV imager) and formerly MDI (magnetograms), which appear in the historical image archive.",
      },
    ],
    dataSources: ["SOHO/LASCO C2 & C3 imagery and movies (NASA GSFC / Helioviewer)"],
    usedIn: ["Coronagraph", "Archive"],
    references: [
      { label: "SOHO/LASCO (NRL)", url: "https://lasco-www.nrl.navy.mil/" },
      { label: "SOHO mission", url: "https://soho.nascom.nasa.gov/" },
    ],
  },
  {
    id: "e-callisto",
    title: "e-CALLISTO Radio Spectrometer Network",
    category: "instruments",
    short:
      "Global network of low-cost radio spectrometers recording solar dynamic spectra to capture metric radio bursts around the clock.",
    aka: ["CALLISTO", "radio spectrometer", "dynamic spectrum"],
    tags: ["radio", "bursts", "spectrogram", "ground-based"],
    body: [
      {
        kind: "para",
        text:
          "e-CALLISTO (Compound Astronomical Low-cost Low-frequency Instrument for Spectroscopy and Transportable Observatory) is a worldwide network of ~150 ground stations. Because stations span all longitudes, at least one is always in daylight, giving 24-hour coverage of the radio Sun.",
      },
      {
        kind: "para",
        text:
          "Each station sweeps a range of radio frequencies (station-dependent, typically tens to several hundred MHz) at roughly 0.25-second cadence, building a dynamic spectrum (frequency vs. time). These spectrograms record type II, III, IV and V solar radio bursts — signatures of electron beams, shocks and CMEs — and are stored as FITS files.",
      },
      {
        kind: "para",
        text:
          "The dashboard ingests CALLISTO FITS to render live/archival spectrograms (Solar Radio), the interactive e-CALLISTO Analyzer, and the machine-learning Burst Detector.",
      },
    ],
    dataSources: [
      "e-CALLISTO FITS archive (ETH Zurich)",
      "Official e-CALLISTO daily burst list",
    ],
    usedIn: ["Solar Radio", "e-CALLISTO Analyzer", "Burst Detector"],
    references: [{ label: "e-CALLISTO network", url: "https://www.e-callisto.org/" }],
  },
  {
    id: "l1-solar-wind-monitors",
    title: "L1 Solar-Wind Monitors (ACE / DSCOVR / IMAP)",
    category: "instruments",
    short:
      "Spacecraft at the L1 point sampling the solar wind and interplanetary magnetic field ~15–60 minutes before it reaches Earth.",
    aka: ["DSCOVR", "ACE", "IMAP", "L1", "solar wind monitor"],
    tags: ["solar wind", "IMF", "L1", "in-situ"],
    body: [
      {
        kind: "para",
        text:
          "The Sun–Earth L1 Lagrange point lies ~1.5 million km sunward of Earth (about 1% of the way to the Sun), where a spacecraft hovers in the incoming solar wind. Successive monitors have held this post: ACE (1997), DSCOVR (2015) and IMAP (2025).",
      },
      {
        kind: "list",
        items: [
          "A plasma instrument (e.g. a Faraday cup) measures solar-wind bulk speed, proton density and temperature.",
          "A fluxgate magnetometer measures the interplanetary magnetic field vector (Bx, By, Bz in GSM coordinates, and total field Bt).",
        ],
      },
      {
        kind: "para",
        text:
          "Because L1 is upstream, its measurements give roughly 15–60 minutes of lead time — the physical basis for real-time geomagnetic-storm warning. The dashboard uses NOAA's propagated (time-shifted to the bow shock) solar-wind product for its real-time speed, Bt and Bz series.",
      },
    ],
    dataSources: [
      "NOAA SWPC propagated-solar-wind JSON (products/geospace)",
      "Active real-time L1 monitor (IMAP)",
    ],
    usedIn: ["Overview", "Solar Wind", "Forecast"],
    references: [
      { label: "SWPC solar wind", url: "https://www.swpc.noaa.gov/products/real-time-solar-wind" },
    ],
  },
  {
    id: "drao-f107",
    title: "DRAO Penticton Radio Telescope (F10.7)",
    category: "instruments",
    short:
      "Ground radiometer that measures the 10.7 cm solar radio flux daily — the longest-running numerical index of solar activity.",
    aka: ["Penticton", "10.7 cm flux", "2800 MHz", "solar radio flux"],
    tags: ["radio flux", "F10.7", "ground-based", "index"],
    body: [
      {
        kind: "para",
        text:
          "The Dominion Radio Astrophysical Observatory (DRAO) in Penticton, British Columbia has measured the Sun's total 10.7 cm (2800 MHz) radio emission every day since 1947 (originally from Ottawa). Three flux determinations are made around local noon.",
      },
      {
        kind: "para",
        text:
          "The F10.7 index, expressed in solar flux units (1 sfu = 10⁻²² W m⁻² Hz⁻¹), tracks emission from the chromosphere and low corona and correlates closely with solar EUV output and sunspot number. It is a key driver of ionospheric and thermospheric models used for satellite drag and radio propagation.",
      },
    ],
    dataSources: ["NOAA SWPC F10.7 feed", "SILSO / SWPC solar-cycle progression"],
    usedIn: ["Solar Radio", "Solar Cycle", "Overview"],
    references: [
      { label: "F10.7 (NRCan)", url: "https://www.spaceweather.gc.ca/forecast-prevision/solar-solaire/solarflux/sx-en.php" },
    ],
  },
  {
    id: "ground-magnetometers",
    title: "Ground Geomagnetic Observatories",
    category: "instruments",
    short:
      "A worldwide network of surface magnetometers whose records are combined into the planetary Kp and Dst indices.",
    aka: ["INTERMAGNET", "magnetic observatory", "K-index station"],
    tags: ["magnetic field", "ground-based", "Kp", "Dst"],
    body: [
      {
        kind: "para",
        text:
          "Hundreds of magnetic observatories continuously record variations in Earth's surface magnetic field. Standardized, high-quality stations are coordinated internationally (e.g. via INTERMAGNET), providing the raw H-component variations behind the geomagnetic indices.",
      },
      {
        kind: "list",
        items: [
          "A network of 13 mid-latitude (subauroral) observatories feeds the planetary Kp index computed at GFZ Potsdam.",
          "Four low-latitude stations (Honolulu, San Juan, Hermanus, Kakioka) feed the Dst ring-current index maintained at Kyoto WDC.",
        ],
      },
      {
        kind: "para",
        text:
          "These indices reach the dashboard through NOAA SWPC (estimated real-time Kp) and the Kyoto/ancillary Dst feeds; the derivation is described under the geomagnetic-index method.",
      },
    ],
    dataSources: ["NOAA SWPC planetary K-index", "Kyoto WDC / real-time Dst"],
    usedIn: ["Geomagnetic", "Overview", "Forecast"],
    references: [
      { label: "GFZ Kp index", url: "https://kp.gfz-potsdam.de/en/" },
      { label: "Kyoto WDC (Dst)", url: "https://wdc.kugi.kyoto-u.ac.jp/dstdir/" },
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Parameters & indices
// ─────────────────────────────────────────────────────────────────────────────

const PARAMETERS: ReferenceEntry[] = [
  {
    id: "xray-flux",
    title: "Soft X-ray Flux & Flare Classification",
    category: "parameters",
    short:
      "Whole-Sun 1–8 Å irradiance and its A/B/C/M/X class — the primary measure of solar flare magnitude and radio-blackout risk.",
    aka: ["flare class", "A B C M X", "R-scale", "radio blackout"],
    tags: ["X-ray", "flare", "R-scale"],
    body: [
      {
        kind: "para",
        text:
          "A solar flare is a sudden release of magnetic energy that brightens the Sun across the spectrum. Its size is graded by the peak of the GOES 1–8 Å soft X-ray irradiance (in W/m²) on a logarithmic letter scale, each letter a factor of ten, with a linear multiplier (e.g. M5, X2).",
      },
      {
        kind: "table",
        caption: "Flare classes and associated NOAA radio-blackout (R) levels",
        columns: ["Class", "1–8 Å peak (W/m²)", "R level", "Effect on HF radio"],
        rows: [
          ["A", "< 10⁻⁷", "—", "None"],
          ["B", "10⁻⁷ – 10⁻⁶", "—", "Negligible"],
          ["C", "10⁻⁶ – 10⁻⁵", "—", "Minor / none"],
          ["M", "10⁻⁵ – 10⁻⁴", "R1–R2", "Limited dayside HF blackout"],
          ["X", "≥ 10⁻⁴", "R3–R5", "Wide-area to complete HF blackout"],
        ],
      },
      {
        kind: "para",
        text:
          "Enhanced X-rays ionize the sunlit D-region of the ionosphere, absorbing high-frequency (HF) radio signals — a 'radio blackout'. NOAA's R-scale maps flare peak flux to impact: R1 at M1 (10⁻⁵), R2 at M5, R3 at X1 (10⁻⁴), R4 at X10, R5 at X20. Only the sunlit hemisphere is affected, and the blackout fades as the flare decays.",
      },
    ],
    dataSources: ["GOES XRS long channel (1–8 Å)"],
    usedIn: ["Overview", "X-ray & Proton", "Forecast"],
    references: [
      { label: "NOAA space weather scales", url: "https://www.swpc.noaa.gov/noaa-scales-explanation" },
    ],
  },
  {
    id: "proton-flux",
    title: "Solar Proton Flux & Radiation Storms (S-scale)",
    category: "parameters",
    short:
      "Integral flux of >10 MeV solar protons, defining NOAA solar radiation storm levels S1–S5.",
    aka: ["SEP", "proton event", "radiation storm", "S-scale", "pfu"],
    tags: ["protons", "radiation", "S-scale"],
    body: [
      {
        kind: "para",
        text:
          "Flares and CME-driven shocks accelerate protons to high energies — solar energetic particles (SEPs). When the >10 MeV integral flux measured at GOES reaches 10 pfu (particles cm⁻² s⁻¹ sr⁻¹), NOAA declares a solar radiation storm. Higher-energy channels (>50, >100 MeV) indicate deeper-penetrating particles.",
      },
      {
        kind: "table",
        caption: "NOAA solar radiation storm (S) scale — >10 MeV flux",
        columns: ["Level", "Flux (pfu)", "Typical impact"],
        rows: [
          ["S1 Minor", "10", "Minor HF impact at poles"],
          ["S2 Moderate", "10²", "Possible passenger-radiation at high-latitude flights"],
          ["S3 Strong", "10³", "Radiation hazard to astronauts (EVA); polar HF degraded"],
          ["S4 Severe", "10⁴", "Elevated crew/avionics risk; polar blackout"],
          ["S5 Extreme", "10⁵", "Unavoidable high radiation risk; satellite errors"],
        ],
      },
      {
        kind: "para",
        text:
          "Because protons travel near light speed along the interplanetary field, a well-connected event can reach Earth within tens of minutes of the flare — often before the associated CME. Impacts include polar-cap radio absorption (PCA), single-event upsets in electronics, and radiation exposure for astronauts and polar-route aviation.",
      },
    ],
    dataSources: ["GOES integral proton flux (>10, >50, >100 MeV)"],
    usedIn: ["Overview", "X-ray & Proton", "Forecast"],
    references: [
      { label: "SWPC proton flux", url: "https://www.swpc.noaa.gov/products/goes-proton-flux" },
    ],
  },
  {
    id: "electron-flux",
    title: "Energetic Electron Flux (>2 MeV)",
    category: "parameters",
    short:
      "Geostationary >2 MeV electron flux that governs internal (deep-dielectric) charging of satellites.",
    aka: ["killer electrons", "internal charging", "MeV electrons"],
    tags: ["electrons", "radiation", "satellites"],
    body: [
      {
        kind: "para",
        text:
          "Following geomagnetic storms, relativistic 'killer' electrons in the outer radiation belt can be enhanced for days. The GOES >2 MeV integral flux (e⁻ cm⁻² s⁻¹ sr⁻¹) is the standard monitor of this population at geostationary orbit.",
      },
      {
        kind: "para",
        text:
          "When the daily fluence stays high, these electrons penetrate spacecraft shielding and accumulate charge deep inside insulators and ungrounded conductors; a subsequent discharge can damage electronics. A flux above ~1,000 pfu is treated as an elevated internal-charging environment.",
      },
    ],
    dataSources: ["GOES >2 MeV integral electron flux"],
    usedIn: ["X-ray & Proton"],
    references: [
      { label: "SWPC electron flux", url: "https://www.swpc.noaa.gov/products/goes-electron-flux" },
    ],
  },
  {
    id: "solar-wind-speed",
    title: "Solar Wind Speed, Density & Temperature",
    category: "parameters",
    short:
      "Bulk properties of the plasma streaming from the Sun, measured in situ at L1 and the engine of geomagnetic activity.",
    aka: ["solar wind", "plasma speed", "density"],
    tags: ["solar wind", "plasma", "L1"],
    body: [
      {
        kind: "para",
        text:
          "The solar wind is a continuous outflow of magnetized plasma from the corona. Typical speeds at Earth are ~300–500 km/s for the slow wind and 500–800 km/s for fast streams from coronal holes; CME-driven transients can exceed 1,000 km/s. Proton density is usually a few particles per cm³.",
      },
      {
        kind: "para",
        text:
          "Speed and density set the solar-wind dynamic pressure that compresses the magnetosphere, while high-speed streams sweeping past Earth drive recurrent (27-day) geomagnetic activity. A sudden jump in speed and density together often marks the arrival of an interplanetary shock ahead of a CME.",
      },
    ],
    dataSources: ["NOAA propagated-solar-wind product (L1, time-shifted)"],
    usedIn: ["Overview", "Solar Wind", "Forecast"],
    references: [
      { label: "SWPC solar wind", url: "https://www.swpc.noaa.gov/products/real-time-solar-wind" },
    ],
  },
  {
    id: "imf",
    title: "Interplanetary Magnetic Field (Bt & Bz)",
    category: "parameters",
    short:
      "The Sun's magnetic field carried past Earth by the solar wind; its southward component (Bz < 0) is the master switch for geomagnetic storms.",
    aka: ["IMF", "Bz", "Bt", "southward field", "Parker spiral"],
    tags: ["magnetic field", "IMF", "reconnection"],
    body: [
      {
        kind: "para",
        text:
          "The interplanetary magnetic field (IMF) is the solar magnetic field dragged outward by the solar wind, wound into the Archimedean 'Parker spiral' by the Sun's rotation. Near Earth it is described in GSM coordinates; two quantities are tracked here.",
      },
      {
        kind: "list",
        items: [
          "Bt — the total field magnitude (nT). Quiet values are ~5 nT; strong CMEs can raise it to tens of nT.",
          "Bz — the north–south component. When Bz turns southward (negative) it is anti-parallel to Earth's dayside field, enabling magnetic reconnection that loads energy into the magnetosphere.",
        ],
      },
      {
        kind: "para",
        text:
          "Sustained strong southward Bz combined with high solar-wind speed is the classic recipe for a geomagnetic storm; northward Bz largely shuts the coupling off. This is why Bz is watched more closely than any other single solar-wind parameter.",
      },
    ],
    dataSources: ["NOAA propagated-solar-wind product (Bt, Bz)"],
    usedIn: ["Overview", "Solar Wind", "Forecast"],
    references: [
      { label: "IMF basics (SWPC)", url: "https://www.swpc.noaa.gov/phenomena/solar-wind" },
    ],
  },
  {
    id: "kp-index",
    title: "Kp Index & Geomagnetic Storms (G-scale)",
    category: "parameters",
    short:
      "The 3-hour planetary geomagnetic index (0–9) that defines NOAA geomagnetic storm levels G1–G5.",
    aka: ["Kp", "planetary K", "G-scale", "geomagnetic storm"],
    tags: ["geomagnetic", "Kp", "G-scale"],
    body: [
      {
        kind: "para",
        text:
          "Kp is a planetary index of geomagnetic activity derived every 3 hours from 13 subauroral magnetometer stations. It runs 0–9 in thirds (0, 0+, 1−, 1, 1+, …) on a quasi-logarithmic scale, summarizing how disturbed Earth's field is worldwide.",
      },
      {
        kind: "table",
        caption: "NOAA geomagnetic storm (G) scale",
        columns: ["Level", "Kp", "Representative effects"],
        rows: [
          ["G1 Minor", "5", "Weak power-grid fluctuations; aurora at high latitudes"],
          ["G2 Moderate", "6", "Aurora to mid-latitudes; HF fade at high latitude"],
          ["G3 Strong", "7", "Voltage corrections needed; satellite drag; aurora lower"],
          ["G4 Severe", "8", "Widespread grid stress; GPS/HF problems; broad aurora"],
          ["G5 Extreme", "9", "Grid collapse risk; aurora to low latitudes"],
        ],
      },
      {
        kind: "para",
        text:
          "The dashboard shows both an estimated real-time Kp and a short-term predicted Kp derived from L1 solar-wind coupling. Aurora visibility, satellite drag and grid impacts all scale with Kp.",
      },
    ],
    dataSources: ["NOAA SWPC estimated planetary K-index", "Predicted Kp (coupling model)"],
    usedIn: ["Overview", "Geomagnetic", "Forecast"],
    references: [
      { label: "SWPC planetary K-index", url: "https://www.swpc.noaa.gov/products/planetary-k-index" },
    ],
  },
  {
    id: "dst-index",
    title: "Dst Index (Ring Current)",
    category: "parameters",
    short:
      "Hourly measure of the storm-time ring current; the standard gauge of geomagnetic storm intensity and phase.",
    aka: ["Dst", "SYM-H", "ring current", "storm main phase"],
    tags: ["geomagnetic", "Dst", "storm"],
    body: [
      {
        kind: "para",
        text:
          "The Disturbance Storm Time (Dst) index averages the horizontal-field depression at four low-latitude observatories. During a geomagnetic storm, energetic ions form an enhanced westward ring current that suppresses the surface field, driving Dst negative. Its 1-minute analog is SYM-H.",
      },
      {
        kind: "table",
        caption: "Approximate storm intensity by minimum Dst",
        columns: ["Dst minimum (nT)", "Storm class"],
        rows: [
          ["> −20", "Quiet"],
          ["−20 to −50", "Weak"],
          ["−50 to −100", "Moderate"],
          ["−100 to −250", "Intense"],
          ["< −250", "Superstorm"],
        ],
      },
      {
        kind: "para",
        text:
          "The Dst profile traces a storm's phases: a brief positive 'sudden commencement' as the shock compresses the magnetosphere, a sharp drop during the main phase as the ring current builds, then a gradual recovery over hours to days.",
      },
    ],
    dataSources: ["Kyoto WDC / real-time Dst feed"],
    usedIn: ["Geomagnetic", "Overview"],
    references: [{ label: "Kyoto WDC (Dst)", url: "https://wdc.kugi.kyoto-u.ac.jp/dstdir/" }],
  },
  {
    id: "f107",
    title: "F10.7 Solar Radio Flux",
    category: "parameters",
    short:
      "The 10.7 cm radio flux (sfu) — a robust, weather-independent proxy for solar EUV output and overall activity level.",
    aka: ["F10.7", "10.7 cm", "solar flux unit", "sfu"],
    tags: ["radio flux", "index", "EUV proxy"],
    body: [
      {
        kind: "para",
        text:
          "F10.7 is the Sun's disk-integrated radio emission at 10.7 cm wavelength, reported in solar flux units (1 sfu = 10⁻²² W m⁻² Hz⁻¹). It combines quiet-Sun thermal emission with slowly-varying active-region components and, during flares, a burst component.",
      },
      {
        kind: "para",
        text:
          "Values range from ~65 sfu at deep solar minimum to 200+ sfu near maximum. Because it correlates strongly with the harder-to-measure solar EUV irradiance, F10.7 is a standard input to ionospheric and thermospheric (satellite-drag) models and a convenient day-to-day activity index alongside sunspot number.",
      },
    ],
    dataSources: ["DRAO Penticton via NOAA SWPC F10.7 feed"],
    usedIn: ["Solar Radio", "Solar Cycle", "Overview"],
    references: [
      { label: "F10.7 explanation", url: "https://www.swpc.noaa.gov/phenomena/f107-cm-radio-emissions" },
    ],
  },
  {
    id: "sunspot-number",
    title: "Sunspot Number & Solar Cycle",
    category: "parameters",
    short:
      "The classic count of sunspots and groups that traces the ~11-year solar activity cycle.",
    aka: ["SSN", "Wolf number", "sunspot", "solar cycle 25"],
    tags: ["sunspots", "solar cycle", "index"],
    body: [
      {
        kind: "para",
        text:
          "The (relative) sunspot number is R = k (10 g + s), where g is the number of sunspot groups, s the number of individual spots, and k an observer/instrument factor. This nearly 400-year record is curated today by SILSO (Royal Observatory of Belgium).",
      },
      {
        kind: "para",
        text:
          "Sunspots are regions of intense magnetic field; their number rises and falls over an ~11-year cycle (the current one is Cycle 25). A 13-month running smoothing reveals the underlying trend used to define solar minimum and maximum. Higher sunspot number generally means more flares, CMEs and elevated EUV/F10.7.",
      },
    ],
    dataSources: ["SILSO sunspot number", "NOAA/NASA solar-cycle progression & prediction"],
    usedIn: ["Solar Cycle", "Overview"],
    references: [{ label: "SILSO", url: "https://www.sidc.be/SILSO/" }],
  },
  {
    id: "aia-passbands",
    title: "AIA EUV Passbands",
    category: "parameters",
    short:
      "The seven SDO/AIA extreme-ultraviolet channels and the plasma temperatures / solar features each one reveals.",
    aka: ["171", "193", "211", "304", "94", "131", "335", "wavelength channels"],
    tags: ["EUV", "imaging", "temperature"],
    body: [
      {
        kind: "para",
        text:
          "Each AIA EUV channel is centred on emission from specific highly-ionized ions, so choosing a wavelength selects a temperature 'slice' of the solar atmosphere. This is how the same Sun looks completely different from channel to channel.",
      },
      {
        kind: "table",
        caption: "AIA EUV / UV channels",
        columns: ["Wavelength (Å)", "Primary ion", "Region / temperature", "What it shows"],
        rows: [
          ["94", "Fe XVIII", "Flaring corona, ~6 MK", "Hot flare plasma"],
          ["131", "Fe VIII / XX / XXIII", "~0.4 & 10 MK", "Flares, transition region"],
          ["171", "Fe IX", "Quiet corona, ~0.6 MK", "Coronal loops, quiet Sun"],
          ["193", "Fe XII / XXIV", "Corona, ~1.2 & 20 MK", "Corona; dark coronal holes"],
          ["211", "Fe XIV", "Active corona, ~2 MK", "Active-region corona"],
          ["304", "He II", "Chromosphere, ~0.05 MK", "Filaments, prominences"],
          ["335", "Fe XVI", "Active corona, ~2.5 MK", "Active-region corona"],
        ],
      },
      {
        kind: "para",
        text:
          "For example, 171 Å traces the graceful loops of the quiet corona, 193 Å makes coronal holes appear as dark patches (sources of fast solar wind), and 304 Å highlights the cooler chromospheric filaments and prominences.",
      },
    ],
    dataSources: ["SDO/AIA imagery"],
    usedIn: ["Solar Images", "Data Analysis"],
    references: [{ label: "AIA channels (LMSAL)", url: "https://aia.lmsal.com/public/instrument.htm" }],
  },
  {
    id: "radio-burst-types",
    title: "Solar Radio Burst Types (II–V)",
    category: "parameters",
    short:
      "The morphological classes of metric radio bursts seen in dynamic spectra and what each reveals about the eruption.",
    aka: ["type II", "type III", "type IV", "type V", "CTM"],
    tags: ["radio", "bursts", "spectrogram"],
    body: [
      {
        kind: "para",
        text:
          "Solar radio bursts appear as structured features in a frequency–time dynamic spectrum. Because higher plasma frequencies correspond to denser (lower) layers of the corona, a burst's drift in frequency tracks the source moving outward through the corona.",
      },
      {
        kind: "table",
        caption: "Common metric radio burst types",
        columns: ["Type", "Appearance", "Physical driver"],
        rows: [
          ["II", "Slow frequency drift, minutes", "CME/flare shock exciting plasma emission"],
          ["III", "Fast drift, seconds", "Beams of fast electrons on open field lines"],
          ["IV", "Broadband continuum, long-lived", "Electrons trapped in loops or a moving CME"],
          ["V", "Short continuum after a type III", "Electrons briefly trapped behind III beams"],
        ],
      },
      {
        kind: "para",
        text:
          "Type III bursts flag flare energy release; type II bursts are a key indicator of a shock and often an associated CME; moving type IV continua accompany erupting material. The e-CALLISTO tools and Burst Detector in this dashboard focus on detecting and classifying these signatures.",
      },
    ],
    dataSources: ["e-CALLISTO dynamic spectra", "Official e-CALLISTO burst list"],
    usedIn: ["Solar Radio", "e-CALLISTO Analyzer", "Burst Detector"],
    references: [{ label: "e-CALLISTO", url: "https://www.e-callisto.org/" }],
  },
  {
    id: "cme",
    title: "Coronal Mass Ejections (CMEs)",
    category: "parameters",
    short:
      "Large eruptions of coronal plasma and magnetic field; their speed, width and direction determine geomagnetic-storm risk and arrival time.",
    aka: ["CME", "halo CME", "ICME", "arrival time"],
    tags: ["CME", "coronagraph", "forecast"],
    body: [
      {
        kind: "para",
        text:
          "A coronal mass ejection hurls billions of tonnes of magnetized plasma into interplanetary space. Coronagraphs (LASCO) measure its plane-of-sky speed and angular width; a full 'halo' appearance suggests it is directed toward or away from Earth.",
      },
      {
        kind: "list",
        items: [
          "Speed — radial speed (often quoted at 21.5 solar radii), from a few hundred to >2,000 km/s.",
          "Half-angle — the cone half-width describing how broad the ejection is.",
          "Source location & direction — whether the CME is Earth-directed.",
          "Predicted arrival — modelled shock/CME arrival time at Earth (e.g. WSA-Enlil), typically 1–4 days out.",
        ],
      },
      {
        kind: "para",
        text:
          "The dashboard's forecast view lists modelled CMEs from NASA's DONKI database with these parameters and, for Earth-directed events, an estimated arrival and expected Kp. A fast, Earth-directed CME carrying strong southward field is the leading cause of major geomagnetic storms.",
      },
    ],
    dataSources: ["NASA DONKI CME analysis (WSA-Enlil arrivals)", "SOHO/LASCO coronagraph"],
    usedIn: ["Forecast", "Coronagraph"],
    references: [{ label: "NASA DONKI", url: "https://ccmc.gsfc.nasa.gov/tools/DONKI/" }],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Methods & products
// ─────────────────────────────────────────────────────────────────────────────

const METHODS: ReferenceEntry[] = [
  {
    id: "difference-imaging",
    title: "Difference Imaging (Running & Base)",
    category: "methods",
    short:
      "Subtracting an earlier frame from a later one to expose faint motion — EUV waves, dimmings and erupting fronts.",
    aka: ["running difference", "base difference", "EUV wave"],
    tags: ["imaging", "SunPy", "analysis"],
    body: [
      {
        kind: "para",
        text:
          "Difference imaging removes the static background of a solar image so subtle time-varying structure stands out. The Data Analysis tools implement two variants using SunPy map arithmetic.",
      },
      {
        kind: "list",
        items: [
          "Running difference — each frame minus the immediately preceding frame; emphasizes fast-moving fronts such as EUV (coronal) waves and CME leading edges.",
          "Base difference — each frame minus a fixed pre-event frame; reveals cumulative changes such as coronal dimmings left behind by an eruption.",
        ],
      },
      {
        kind: "para",
        text:
          "The result is displayed on a symmetric (bipolar) colour scale so brightenings and depletions relative to the reference appear as opposite colours.",
      },
    ],
    dataSources: ["SDO/AIA sequences (SunPy / JSOC)"],
    usedIn: ["Data Analysis"],
  },
  {
    id: "composite-imaging",
    title: "Composite Imaging (AIA + HMI Contours)",
    category: "methods",
    short:
      "Overlaying reprojected HMI magnetic-field contours on an AIA EUV image to connect coronal structures to their photospheric roots.",
    aka: ["composite", "magnetogram overlay", "reprojection", "WCS"],
    tags: ["imaging", "magnetogram", "SunPy"],
    body: [
      {
        kind: "para",
        text:
          "Coronal loops seen in AIA are anchored in photospheric magnetic fields measured by HMI, but the two instruments have different plate scales and pointing. The composite tool reprojects an HMI line-of-sight magnetogram onto the AIA world-coordinate system so the two align pixel-for-pixel.",
      },
      {
        kind: "para",
        text:
          "Positive- and negative-polarity contours are then drawn at chosen field-strength (Gauss) levels over the EUV image. This makes it easy to see how bright coronal features connect opposite magnetic polarities and to identify the strong-field active regions likely to flare.",
      },
    ],
    dataSources: ["SDO/AIA + SDO/HMI (SunPy reproject)"],
    usedIn: ["Data Analysis"],
  },
  {
    id: "active-region-detection",
    title: "Active Region Detection",
    category: "methods",
    short:
      "Locating and labelling active regions from catalog metadata and image thresholding.",
    aka: ["active region", "HEK", "NOAA AR", "segmentation"],
    tags: ["detection", "active region", "analysis"],
    body: [
      {
        kind: "para",
        text:
          "The active-region tool marks the strong-field regions that produce most flares and CMEs using two complementary approaches.",
      },
      {
        kind: "list",
        items: [
          "Catalog markers — NOAA active-region numbers and positions queried from the Heliophysics Events Knowledgebase (HEK) and plotted on the disk.",
          "Intensity thresholding — bright EUV features segmented with a brightness threshold and connected-component labelling (scipy) to outline candidate regions directly from the image.",
        ],
      },
    ],
    dataSources: ["HEK event catalog", "SDO/AIA imagery"],
    usedIn: ["Data Analysis"],
    references: [{ label: "Heliophysics Events Knowledgebase", url: "https://www.lmsal.com/hek/" }],
  },
  {
    id: "movie-generation",
    title: "Time-lapse Movie Generation",
    category: "methods",
    short:
      "Assembling a sequence of solar frames into an MP4 or GIF to animate evolving activity.",
    aka: ["MapSequence", "animation", "timelapse", "MP4", "GIF"],
    tags: ["movies", "SunPy", "analysis"],
    body: [
      {
        kind: "para",
        text:
          "A run of consecutive images is loaded as a SunPy MapSequence, normalized to a common intensity scale, and rendered frame-by-frame. Frames are encoded to MP4 (via ffmpeg) or animated GIF for sharing.",
      },
      {
        kind: "para",
        text:
          "Movies are the most intuitive way to follow a dynamic event — an erupting filament, an EUV wave, or a CME crossing the LASCO field — and can be combined with difference imaging for extra contrast.",
      },
    ],
    dataSources: ["SDO/AIA sequences", "SOHO/LASCO frames"],
    usedIn: ["Data Analysis", "Coronagraph"],
  },
  {
    id: "radio-processing",
    title: "Radio Spectrogram Processing (Background & RFI)",
    category: "methods",
    short:
      "Turning raw CALLISTO counts into a clean dynamic spectrum via background subtraction, RFI masking and intensity scaling.",
    aka: ["background subtraction", "RFI", "quiet-sun", "dB", "calibration"],
    tags: ["radio", "processing", "spectrogram"],
    body: [
      {
        kind: "para",
        text:
          "Raw e-CALLISTO data are recorded as digitizer counts that mix the solar signal with instrument gain, the quiet-Sun background and terrestrial radio-frequency interference (RFI). The e-CALLISTO Analyzer cleans this up before display.",
      },
      {
        kind: "list",
        items: [
          "Background subtraction — a per-frequency background (mean, median or a robust estimator) is computed over time and removed, flattening the passband and revealing transient bursts.",
          "RFI mitigation — persistently contaminated frequency channels are masked out so narrowband interference does not swamp the colour scale.",
          "Intensity scaling — data are shown in raw digits or converted to decibels, with adjustable vmin/vmax for contrast.",
        ],
      },
    ],
    dataSources: ["e-CALLISTO FITS spectra"],
    usedIn: ["e-CALLISTO Analyzer", "Solar Radio"],
  },
  {
    id: "ml-burst-detection",
    title: "Machine-Learning Burst Detection",
    category: "methods",
    short:
      "A neural-network model that scans daily CALLISTO spectrograms to detect and score candidate radio bursts, corroborated across stations.",
    aka: ["burst predictor", "CNN", "classification", "scorecard", "precision recall"],
    tags: ["machine learning", "radio", "detection"],
    body: [
      {
        kind: "para",
        text:
          "The Burst Detector runs the day's CALLISTO spectrograms through a trained classifier (served by a companion Burst Identifier microservice). Each spectrogram segment receives a burst probability and alert level.",
      },
      {
        kind: "para",
        text:
          "To suppress false alarms from local RFI, detections are corroborated across multiple stations before being grouped into events; a 'raw' mode exposes the unfiltered model output. Performance is tracked against the official e-CALLISTO burst list on a trailing scorecard reporting precision (fraction of predicted events that were real) and recall (fraction of official bursts the model caught).",
      },
    ],
    dataSources: ["e-CALLISTO spectra", "Burst Identifier ML service", "Official burst list"],
    usedIn: ["Burst Detector"],
  },
  {
    id: "coronagraph-cme-detection",
    title: "Coronagraph CME Detection",
    category: "methods",
    short:
      "Using running-difference coronagraph movies and CME catalogs to identify and parametrize eruptions.",
    aka: ["CME detection", "halo CME", "CACTus", "CDAW", "DONKI"],
    tags: ["coronagraph", "CME", "detection"],
    body: [
      {
        kind: "para",
        text:
          "CMEs are faint against the structured corona, so they are found in running-difference LASCO movies where outward-moving brightness enhancements stand out frame to frame. A CME that appears to surround the occulter as a full 'halo' is heading roughly toward or away from Earth.",
      },
      {
        kind: "para",
        text:
          "Detected events are parametrized — plane-of-sky speed, angular width, position angle — either by automated detectors (e.g. CACTus) or human analysts (CDAW), and modelled arrivals are catalogued in NASA's DONKI. The dashboard surfaces LASCO imagery/movies plus DONKI-derived CME parameters and arrival predictions.",
      },
    ],
    dataSources: ["SOHO/LASCO C2 & C3", "NASA DONKI CME catalog"],
    usedIn: ["Coronagraph", "Forecast"],
    references: [{ label: "NASA DONKI", url: "https://ccmc.gsfc.nasa.gov/tools/DONKI/" }],
  },
  {
    id: "kp-forecast",
    title: "Short-term Kp Forecast (Solar-Wind Coupling)",
    category: "methods",
    short:
      "Predicting near-term geomagnetic activity from real-time L1 solar wind using a magnetospheric coupling function.",
    aka: ["predicted Kp", "Newell coupling", "coupling function", "dΦ/dt"],
    tags: ["forecast", "geomagnetic", "coupling"],
    body: [
      {
        kind: "para",
        text:
          "Geomagnetic activity a short time ahead can be estimated from the solar wind measured now at L1. A coupling function quantifies how effectively the solar wind transfers energy into the magnetosphere, combining speed and the southward field.",
      },
      {
        kind: "formula",
        expr: "dΦ/dt = v^(4/3) · Bt^(2/3) · sin^(8/3)(θc / 2)",
        note:
          "Newell coupling function: v = solar-wind speed, Bt = IMF magnitude, θc = IMF clock angle (its rotation from north). Larger values ⇒ stronger driving.",
      },
      {
        kind: "para",
        text:
          "The coupling rate is mapped to a predicted Kp (and the corresponding NOAA G-level) for roughly the next 1–3 hours, giving lead time from L1 before the disturbance registers on the ground.",
      },
    ],
    dataSources: ["L1 propagated solar wind (speed, Bt, Bz)"],
    usedIn: ["Forecast", "Overview"],
    references: [
      { label: "Newell et al. 2007 coupling", url: "https://doi.org/10.1029/2006JA012015" },
    ],
  },
  {
    id: "geomagnetic-indices",
    title: "Geomagnetic Index Derivation (K → Kp, Dst)",
    category: "methods",
    short:
      "How raw magnetometer records are reduced into the standardized Kp and Dst indices.",
    aka: ["K-index", "Kp derivation", "Dst computation", "quiet-day baseline"],
    tags: ["geomagnetic", "index", "processing"],
    body: [
      {
        kind: "para",
        text:
          "Ground magnetometer traces are reduced to indices so activity can be compared globally and over time.",
      },
      {
        kind: "list",
        items: [
          "K-index — at each station, the range of irregular horizontal-field variation over 3 hours (after removing the regular quiet-day curve) is mapped to a quasi-logarithmic 0–9 value.",
          "Kp — the standardized K values from 13 subauroral stations are averaged into the planetary Kp, cancelling local-time and latitude effects.",
          "Dst — the horizontal-field depression at four low-latitude stations is averaged and corrected for quiet-time and secular baselines to isolate the ring-current signal.",
        ],
      },
      {
        kind: "para",
        text:
          "Operationally, NOAA issues an estimated real-time Kp within minutes, while the definitive Kp and Dst are finalized later by GFZ Potsdam and Kyoto WDC respectively.",
      },
    ],
    dataSources: ["Ground magnetometer networks via NOAA SWPC & Kyoto WDC"],
    usedIn: ["Geomagnetic"],
    references: [{ label: "GFZ Kp", url: "https://kp.gfz-potsdam.de/en/" }],
  },
  {
    id: "solar-cycle-prediction",
    title: "Solar-Cycle Progression & Prediction",
    category: "methods",
    short:
      "Smoothing observed sunspot/F10.7 records and overlaying the official predicted range to place the current cycle in context.",
    aka: ["13-month smoothing", "cycle prediction", "SWPC panel", "Cycle 25"],
    tags: ["solar cycle", "prediction", "forecast"],
    body: [
      {
        kind: "para",
        text:
          "The long-term progression of the solar cycle is tracked by smoothing the monthly sunspot number and F10.7 flux with the conventional 13-month running mean, which removes short-term scatter and defines the cycle's minimum and maximum.",
      },
      {
        kind: "para",
        text:
          "Observed smoothed values are shown against the official NOAA/NASA prediction panel's expected curve and its high/low uncertainty band. This indicates whether the current cycle is running stronger or weaker than forecast — context for expected flare and storm frequency over the coming years.",
      },
    ],
    dataSources: ["SILSO sunspot number", "NOAA/NASA solar-cycle prediction panel", "F10.7"],
    usedIn: ["Solar Cycle"],
    references: [
      { label: "SWPC solar-cycle progression", url: "https://www.swpc.noaa.gov/products/solar-cycle-progression" },
    ],
  },
];

export const REFERENCE_ENTRIES: ReferenceEntry[] = [
  ...INSTRUMENTS,
  ...PARAMETERS,
  ...METHODS,
];

/** Lowercased haystack for an entry, used by the client-side search filter. */
export function entrySearchText(entry: ReferenceEntry): string {
  const parts: string[] = [entry.title, entry.short, ...(entry.aka ?? []), ...(entry.tags ?? [])];
  for (const block of entry.body) {
    if (block.kind === "para") parts.push(block.text);
    else if (block.kind === "list") parts.push(...block.items);
    else if (block.kind === "formula") parts.push(block.expr, block.note ?? "");
    else if (block.kind === "table") {
      if (block.caption) parts.push(block.caption);
      parts.push(...block.columns, ...block.rows.flat());
    }
  }
  parts.push(...(entry.dataSources ?? []), ...(entry.usedIn ?? []));
  return parts.join(" ").toLowerCase();
}
