/**
 * Projection math — direct port of Python position_engine.py:
 *   _milepost_latlon  →  milepostToLatLon
 *   project_to_leg    →  projectToLeg
 *
 * Precision: great-circle (haversine) distance; equirectangular segment projection.
 * Matches Python output within 0.001° lat/lon and 0.01 mi by construction.
 */
import type { Polyline, LatLon, ProjectionResult } from './types.js';

/** Earth radius in miles (matches Python: 3958.7613). */
const EARTH_MI = 3958.7613;

/** Haversine distance in miles between two (lat, lon) points. */
function haversineMi(
  aLat: number, aLon: number,
  bLat: number, bLon: number,
): number {
  const toR = Math.PI / 180;
  const dlat = (bLat - aLat) * toR;
  const dlon = (bLon - aLon) * toR;
  const h =
    Math.sin(dlat / 2) ** 2 +
    Math.cos(aLat * toR) * Math.cos(bLat * toR) * Math.sin(dlon / 2) ** 2;
  return 2 * EARTH_MI * Math.asin(Math.min(1.0, Math.sqrt(h)));
}

/**
 * Port of Python _project_point_seg(qlat, qlon, lat1, lon1, lat2, lon2).
 * Projects (qlat, qlon) onto segment 1→2 (equirectangular).
 * Returns { t ∈ [0,1], footLat, footLon }.
 */
function projectPointSeg(
  qlat: number, qlon: number,
  lat1: number, lon1: number,
  lat2: number, lon2: number,
): { t: number; footLat: number; footLon: number } {
  const kx = Math.cos(((lat1 + lat2) / 2) * (Math.PI / 180));
  const ax = (lon2 - lon1) * kx;
  const ay = lat2 - lat1;
  const bx = (qlon - lon1) * kx;
  const by = qlat - lat1;
  const denom = ax * ax + ay * ay;
  const t = denom === 0 ? 0.0 : Math.max(0.0, Math.min(1.0, (ax * bx + ay * by) / denom));
  return {
    t,
    footLat: lat1 + t * (lat2 - lat1),
    footLon: lon1 + t * (lon2 - lon1),
  };
}

/**
 * Port of Python _milepost_latlon(poly, mile).
 *
 * Interpolates on-track (lat, lon) at a given milepost along the leg polyline.
 * poly: [[anchor_mile, lat, lon], ...]
 * Clamps to [poly[0].mile, poly[-1].mile].
 */
export function milepostToLatLon(poly: Polyline, mile: number): LatLon {
  if (poly.length === 0) throw new Error('milepostToLatLon: empty polyline');

  // Clamp below start
  if (mile <= poly[0][0]) return { lat: poly[0][1], lon: poly[0][2] };

  // Clamp above end
  const last = poly[poly.length - 1];
  if (mile >= last[0]) return { lat: last[1], lon: last[2] };

  // Find bracketing segment and interpolate linearly
  for (let i = 0; i < poly.length - 1; i++) {
    const [m1, la1, lo1] = poly[i];
    const [m2, la2, lo2] = poly[i + 1];
    if (m1 <= mile && mile <= m2) {
      const f = m2 !== m1 ? (mile - m1) / (m2 - m1) : 0.0;
      return {
        lat: la1 + f * (la2 - la1),
        lon: lo1 + f * (lo2 - lo1),
      };
    }
  }

  // Fallback (should not be reached)
  return { lat: last[1], lon: last[2] };
}

/**
 * Port of Python project_to_leg(poly, lat, lon).
 *
 * Nearest point on the leg polyline to (lat, lon).
 * Returns { mile, offtrackMi, side } where:
 *   side = 'ahead'  if offtrack < 0.3 mi (Python deadband)
 *   side = 'left'   if cross-product > 0 (feature is to the left of travel)
 *   side = 'right'  if cross-product ≤ 0
 *
 * Returns { mile: 0, offtrackMi: 0, side: 'ahead' } if poly has < 2 vertices.
 */
export function projectToLeg(poly: Polyline, lat: number, lon: number): ProjectionResult {
  if (poly.length < 2) {
    return { mile: poly[0]?.[0] ?? 0, offtrackMi: 0, side: 'ahead' };
  }

  let bestDist = Infinity;
  let bestMile = 0;
  let bestSide: 'left' | 'right' | 'ahead' = 'ahead';

  for (let i = 0; i < poly.length - 1; i++) {
    const [m1, la1, lo1] = poly[i];
    const [m2, la2, lo2] = poly[i + 1];

    const { t, footLat, footLon } = projectPointSeg(lat, lon, la1, lo1, la2, lo2);
    const d = haversineMi(lat, lon, footLat, footLon);

    if (d < bestDist) {
      bestDist = d;
      bestMile = m1 + t * (m2 - m1);

      // Cross-product to determine side of travel direction:
      // travel vector: (vx, vy); toward-feature vector: (wx, wy)
      // cross = vx*wy - vy*wx  >0 ⇒ feature is to the LEFT
      const kx = Math.cos(((la1 + la2) / 2) * (Math.PI / 180));
      const vx = (lo2 - lo1) * kx;
      const vy = la2 - la1;
      const wx = (lon - footLon) * kx;
      const wy = lat - footLat;
      const cross = vx * wy - vy * wx;

      // Python deadband: d < 0.3 mi → 'ahead'
      if (d < 0.3) {
        bestSide = 'ahead';
      } else {
        bestSide = cross > 0 ? 'left' : 'right';
      }
    }
  }

  return {
    mile:       Math.round(bestMile * 100) / 100,
    offtrackMi: Math.round(bestDist   * 100) / 100,
    side:       bestSide,
  };
}
