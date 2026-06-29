import { WebPlugin } from '@capacitor/core';
import type { AudioSessionPlugin } from './definitions';
export declare class AudioSessionWeb extends WebPlugin implements AudioSessionPlugin {
    private audio;
    private _unlocked;
    /** Unlock AudioContext on first user gesture (iOS Safari requirement) */
    private _ensureUnlocked;
    setMode(_options: {
        mode: 'duck' | 'pause' | 'interrupt-spoken';
    }): Promise<void>;
    play(options: {
        fileUri: string;
    }): Promise<void>;
    pause(): Promise<void>;
    resume(): Promise<void>;
    setRate(options: {
        rate: number;
    }): Promise<void>;
}
