// ── Bundle types (Plan 0 corrected contract — do not modify) ──────────────────

/**
 * Side of the train the feature is on. Values match the real proxy bundle:
 * lowercase 'left'/'right' from the Python engine, plus 'both'/'ahead'/null.
 */
export type UnitSide = 'left' | 'right' | 'both' | 'ahead' | null;

/** Salience score: integer 1 (background) → 5 (unmissable highlight). */
export type Salience = 1 | 2 | 3 | 4 | 5;

export interface SquibUnit {
  id: string;
  kind: 'squib';
  mile: number;
  place: string | null;
  side: UnitSide;
  salience: Salience;
  theme: string | null;
  text: string;
  lat: number;
  lon: number;
  poi_lat?: number;
  poi_lon?: number;
  offtrack_mi?: number;
  audio: string;
  dur_s: number;
}

export interface InterstitialUnit {
  id: string;
  kind: 'interstitial';
  from_mi: number;
  to_mi: number;
  place: string | null;
  side: UnitSide;
  salience: Salience;
  theme: string | null;
  text: string;
  lat: number;
  lon: number;
  poi_lat?: number;
  poi_lon?: number;
  offtrack_mi?: number;
  audio: string;
  dur_s: number;
}

export type Unit = SquibUnit | InterstitialUnit;

export interface Station {
  code: string;
  name: string;
  mile: number;
  lat: number;
  lon: number;
  /** ISO 8601 datetime string, or null for origin/terminus. */
  sched_arr: string | null;
  sched_dep: string | null;
  dwell_min: number;
}

export interface ScheduleBasis {
  kind: 'trip-actual' | 'generic-scheduled';
  /** ISO date strings. Non-empty for trip-actual; empty for generic. */
  valid_dates: string[];
}

export interface BundleLayers {
  guide: unknown;
  lore: unknown;
  science: unknown;
  connections: unknown;
  themes: unknown;
}

/** GeoJSON LineString geometry for the leg route. */
export interface LineStringGeometry {
  type: 'LineString';
  /** [lon, lat] pairs per GeoJSON convention. */
  coordinates: [number, number][];
}

/** position_table row: [elapsed_min, mile, lat, lon] */
export type PositionTableRow = [number, number, number, number];

export interface EtaTableRow {
  station_code: string;
  p10_min: number;
  p50_min: number;
  p90_min: number;
}

export interface Bundle {
  leg: string;
  /** Present in proxy bundles produced before full render. */
  proxy?: boolean;
  schedule_basis: ScheduleBasis;
  stations: Station[];
  geometry: LineStringGeometry;
  units: Unit[];
  layers: BundleLayers;
  /** Rows: [elapsed_min, mile, lat, lon] */
  position_table: PositionTableRow[];
  /** Per-station ETA ensemble (trip-actual only; may be absent/empty for generic). */
  eta_table: EtaTableRow[];
  /** Optional featured deep-dive stories for this leg. */
  deepdives?: DeepDive[];
}

// ── Projection types ──────────────────────────────────────────────────────────

/** Polyline vertex as stored in leg_shapes: [anchor_mile, lat, lon] */
export type PolyVertex = [number, number, number];
export type Polyline = PolyVertex[];

export interface LatLon {
  lat: number;
  lon: number;
}

export interface ProjectionResult {
  mile: number;
  offtrackMi: number;
  side: 'left' | 'right' | 'ahead';
}

// ── Position types ────────────────────────────────────────────────────────────

export interface Position {
  mile: number;
  lat: number;
  lon: number;
  source: 'live' | 'gps' | 'deadreckon' | 'predicted' | 'off-route';
  direction: 1 | -1;
  leg: string;
  stopped: boolean;
}

// ── Scheduler types ───────────────────────────────────────────────────────────

export interface SchedulerSettings {
  /** Fraction of silence budget to fill with interstitials (0–1). */
  fillPct: number;
  /** Empty set = all themes pass. */
  themes: Set<string>;
  /** When true, only salience >= 4 units are considered. */
  highlightOnly: boolean;
}

export interface SchedulerResult {
  nowPlaying: Unit | null;
  queue: Unit[];
  /** Sentinel -Infinity = no active silence. */
  silenceUntilMile: number;
}

// ── ETA types ─────────────────────────────────────────────────────────────────

/**
 * Absolute epoch-ms estimates.
 * trip-actual: real ensemble from eta_table, estimated=false.
 * generic: p10===p50===p90 (single time), estimated=true.
 */
export interface EtaResult {
  p10: number;
  p50: number;
  p90: number;
  estimated: boolean;
}

// ── Favorites types ───────────────────────────────────────────────────────────

export interface DiveCard {
  body: string;
  sources: string[];
  createdAt: number; // unix ms
}

export interface Favorite {
  id: string;
  leg: string;
  unitSnapshot: Unit;
  position: Position;
  kind: 'star' | 'tellmore';
  note?: string;
  createdAt: number; // unix ms
  dive?: DiveCard;
}

// ── Storage adapter interface ─────────────────────────────────────────────────

export interface StorageAdapter {
  save(favorite: Favorite): Promise<void>;
  loadAll(): Promise<Favorite[]>;
  loadById(id: string): Promise<Favorite | null>;
  update(id: string, patch: Partial<Favorite>): Promise<void>;
  delete(id: string): Promise<void>;
}

// ── Deep-dive featured stories ────────────────────────────────────────────────

export interface DeepDiveImage {
  url: string;
  caption: string;
  credit: string;
  license: string;
}

export interface DeepDiveSource {
  title: string;
  url: string;
}

/**
 * An extended featured story (~3–5 min) that rides alongside the position-driven
 * narration as a separate, opt-in layer. Available to Read (body_md) or Listen
 * (audio, when rendered).
 */
export interface DeepDiveAudioAsset {
  type: 'song' | 'speech' | 'field-recording';
  desc: string;
  suggested_source: string;
  insert_after_excerpt: string;
  licensing: string;
}

export interface DeepDive {
  id: string;
  theme: string;
  title: string;
  /** Placement mile along the route. */
  mile: number;
  /** Mile at which the story becomes "available" (typically mile - 8). */
  trigger_mile: number;
  nearest_place: string;
  /** 1–2 sentence teaser shown on the offer banner and card header. */
  hook: string;
  /** Formatted markdown — the READ version. */
  body_md: string;
  /** The spoken version (may differ slightly from body_md). */
  narration_text: string;
  est_listen_min: number;
  /** Rendered audio path; null until rendered (offer still shows "Read"). */
  audio: string | null;
  images: DeepDiveImage[];
  sources: DeepDiveSource[];
  salience: number;
  /** Notes about image licensing status or sourcing needs. */
  image_note?: string;
  /** Suggested audio assets that would enhance the spoken version. */
  audio_assets?: DeepDiveAudioAsset[];
}

// ── Dive grounding (type-only; impl Phase 2) ──────────────────────────────────

export interface DiveGrounding {
  unitText: string;
  connections: unknown;
  lore: unknown;
  science: unknown;
  theme: unknown;
  sources: string[];
}
