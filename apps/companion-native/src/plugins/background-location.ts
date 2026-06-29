/**
 * BackgroundLocation — Capacitor plugin bridge.
 *
 * On iOS: delegates to BackgroundLocationPlugin.swift (CLLocationManager,
 *   allowsBackgroundLocationUpdates=true, UIBackgroundModes: location).
 * On web/Simulator: delegates to BackgroundLocationWeb (synthetic fixed position).
 *
 * Matches the locked Plan 0 F contract:
 *   BackgroundLocation.watch(cb) -> Promise<string handle>
 *   BackgroundLocation.clear(handle) -> Promise<void>
 */
import { registerPlugin } from '@capacitor/core';

export interface LocationFix {
  lat: number;
  lon: number;
  ts: number;    // Unix ms
  speed: number; // m/s, −1 if unavailable
}

interface BackgroundLocationNativePlugin {
  startWatch(): Promise<{ handle: string }>;
  clearWatch(opts: { handle: string }): Promise<void>;
  addListener(event: 'location', cb: (fix: LocationFix) => void): any;
  removeAllListeners(): Promise<void>;
}

const _plugin = registerPlugin<BackgroundLocationNativePlugin>('BackgroundLocation', {
  web: () =>
    import('./background-location-web').then((m) => new m.BackgroundLocationWeb()),
});

export const BackgroundLocation = {
  /** Start receiving GPS fixes in the background. Returns an opaque handle. */
  async watch(cb: (fix: LocationFix) => void): Promise<string> {
    _plugin.addListener('location', cb);
    const { handle } = await _plugin.startWatch();
    return handle;
  },

  /** Stop receiving fixes for the given handle. */
  async clear(handle: string): Promise<void> {
    await _plugin.clearWatch({ handle });
    await _plugin.removeAllListeners();
  },
};
