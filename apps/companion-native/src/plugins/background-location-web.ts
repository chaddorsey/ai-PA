/**
 * BackgroundLocation web implementation (Simulator / browser DevTools).
 * Emits a synthetic stationary fix every 5 s so the app renders without crashing.
 * Not used on a real iOS device — the Swift plugin takes over there.
 */
import { WebPlugin } from '@capacitor/core';
import type { LocationFix } from './background-location';

export class BackgroundLocationWeb extends WebPlugin {
  private timers = new Map<string, ReturnType<typeof setInterval>>();

  async startWatch(): Promise<{ handle: string }> {
    const handle = `web-${Date.now()}`;
    const timer = setInterval(() => {
      this.notifyListeners('location', {
        lat: 37.7749,   // approximately Raton Pass, NM
        lon: -104.9994,
        ts: Date.now(),
        speed: 20,      // m/s ≈ 45 mph
      } satisfies LocationFix);
    }, 5000);
    this.timers.set(handle, timer);
    return { handle };
  }

  async clearWatch(opts: { handle: string }): Promise<void> {
    const timer = this.timers.get(opts.handle);
    if (timer) {
      clearInterval(timer);
      this.timers.delete(opts.handle);
    }
  }
}
