import { registerPlugin } from '@capacitor/core';
const AudioSession = registerPlugin('AudioSession', {
    web: () => import('./web').then(m => new m.AudioSessionWeb()),
});
export * from './definitions';
export { AudioSession };
