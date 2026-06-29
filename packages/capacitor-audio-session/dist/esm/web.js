import { WebPlugin } from '@capacitor/core';
export class AudioSessionWeb extends WebPlugin {
    constructor() {
        super(...arguments);
        this.audio = null;
        this._unlocked = false;
    }
    /** Unlock AudioContext on first user gesture (iOS Safari requirement) */
    _ensureUnlocked() {
        if (this._unlocked)
            return;
        this._unlocked = true;
        // create and immediately discard a silent audio element to satisfy Safari's gesture requirement
        const a = new Audio();
        a.play().catch(() => { });
    }
    async setMode(_options) {
        // No-op in browser; mode is handled natively
    }
    async play(options) {
        this._ensureUnlocked();
        if (this.audio) {
            this.audio.pause();
            this.audio.onended = null;
        }
        this.audio = new Audio(options.fileUri);
        this.audio.onended = () => {
            this.notifyListeners('ended', {});
        };
        await this.audio.play();
    }
    async pause() {
        var _a;
        (_a = this.audio) === null || _a === void 0 ? void 0 : _a.pause();
    }
    async resume() {
        var _a;
        await ((_a = this.audio) === null || _a === void 0 ? void 0 : _a.play());
    }
    async setRate(options) {
        if (this.audio) {
            this.audio.playbackRate = options.rate;
        }
    }
}
