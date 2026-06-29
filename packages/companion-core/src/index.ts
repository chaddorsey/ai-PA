// Re-export all public types from companion-core.
// Implementations (bundle loader, projection, scheduler, etc.) are added in later tasks.

export type {
  // Unit types
  Unit,
  SquibUnit,
  InterstitialUnit,
  UnitSide,
  Salience,
  // Bundle types
  Bundle,
  BundleLayers,
  ScheduleBasis,
  Station,
  LineStringGeometry,
  PositionTableRow,
  EtaTableRow,
  // Projection types
  Polyline,
  PolyVertex,
  LatLon,
  ProjectionResult,
  // Position types
  Position,
  // Scheduler types
  SchedulerSettings,
  SchedulerResult,
  // ETA types
  EtaResult,
  // Favorites types
  Favorite,
  DiveCard,
  StorageAdapter,
  // Dive grounding (type-only)
  DiveGrounding,
} from './types.js';

export { loadBundle, validateBundle } from './bundle.js';
export { milepostToLatLon, projectToLeg } from './projection.js';
export { PositionService } from './position-service.js';
