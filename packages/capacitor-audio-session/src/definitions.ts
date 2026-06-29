export interface AudioSessionPlugin {
  /**
   * Set the audio session mode.
   * duck: lower other audio while playing
   * pause: pause other audio while playing
   * interrupt-spoken: interrupt spoken audio (podcast, Siri) but not music
   */
  setMode(options: { mode: 'duck' | 'pause' | 'interrupt-spoken' }): Promise<void>;

  /**
   * Play audio file. fileUri is a web-root-relative path like /bundles/leg58/audio/x.mp3
   * which maps to Bundle.main/public/... on native.
   */
  play(options: { fileUri: string }): Promise<void>;

  /**
   * Pause current playback.
   */
  pause(): Promise<void>;

  /**
   * Resume paused playback.
   */
  resume(): Promise<void>;

  /**
   * Set playback rate (1.0 = normal).
   */
  setRate(options: { rate: number }): Promise<void>;

  /**
   * Listen for playback events.
   * 'ended': audio file finished playing
   * 'interrupt': system interrupted playback (phone call, etc.)
   */
  addListener(
    eventName: 'ended' | 'interrupt',
    listenerFunc: (data: { shouldResume?: boolean }) => void,
  ): Promise<{ remove: () => void }>;
}
