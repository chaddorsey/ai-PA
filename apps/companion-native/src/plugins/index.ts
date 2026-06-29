/**
 * Plugin index — single import surface for Plan 2 (companion-core) and Plan 4 (companion-web).
 *
 * Usage:
 *   import { BackgroundLocation, AudioSession, BundleStore, LiveActivity } from 'companion-native/src/plugins';
 *
 * All four plugins have matching web stubs so the app works in the browser and Simulator.
 */
export { BackgroundLocation } from './background-location';
export type { LocationFix } from './background-location';

export { AudioSession } from './audio-session';
export type { AudioMode, AudioEventName } from './audio-session';

export { BundleStore } from './bundle-store';

export { LiveActivity } from './live-activity';
export type { LiveActivityState } from './live-activity';
