import Foundation
import Combine

final class FadeManager: ObservableObject {
    @Published var opacity: Double = 1.0
    @Published var isActive: Bool = false

    let totalDuration: TimeInterval

    private var fadeStart: Date?
    private var hoverStart: Date?
    private var opacityAtPause: Double = 1.0
    private var elapsedBeforePause: TimeInterval = 0
    private var timer: AnyCancellable?
    private var isHovering: Bool = false

    private static let frameInterval: TimeInterval = 1.0 / 30.0

    init(totalDuration: TimeInterval) {
        self.totalDuration = totalDuration
    }

    func startFade() {
        opacity = 1.0
        isActive = true
        isHovering = false
        elapsedBeforePause = 0
        fadeStart = Date()
        startTimer()
    }

    func stopFade() {
        isActive = false
        isHovering = false
        opacity = 1.0
        elapsedBeforePause = 0
        fadeStart = nil
        hoverStart = nil
        timer?.cancel()
        timer = nil
    }

    func mouseEntered() {
        guard isActive else { return }
        isHovering = true
        hoverStart = Date()
        opacityAtPause = opacity
        if let fadeStart = fadeStart {
            elapsedBeforePause += Date().timeIntervalSince(fadeStart)
        }
        timer?.cancel()
        timer = nil
        opacity = 1.0
    }

    func mouseExited() {
        guard isActive, isHovering else { return }
        isHovering = false

        let hoverDuration = hoverStart.map { Date().timeIntervalSince($0) } ?? 0
        hoverStart = nil

        if hoverDuration >= 5.0 {
            // Reset fade timer completely
            elapsedBeforePause = 0
            opacity = 1.0
        } else {
            // Resume from interrupted opacity
            opacity = opacityAtPause
        }

        fadeStart = Date()
        startTimer()
    }

    // MARK: - Private

    private func startTimer() {
        timer?.cancel()
        timer = Timer.publish(every: Self.frameInterval, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                self?.tick()
            }
    }

    private func tick() {
        guard isActive, let fadeStart = fadeStart else { return }

        let remaining = totalDuration - elapsedBeforePause
        guard remaining > 0 else {
            opacity = 0.0
            isActive = false
            timer?.cancel()
            timer = nil
            return
        }

        let timeSinceFadeStart = Date().timeIntervalSince(fadeStart)
        let progress = min(timeSinceFadeStart / remaining, 1.0)

        // Ease-in-ease-out curve: 3t^2 - 2t^3
        let eased = 3 * progress * progress - 2 * progress * progress * progress

        let startOpacity = isHovering ? 1.0 : (elapsedBeforePause > 0 ? opacityAtPause : 1.0)
        opacity = max(0.0, startOpacity * (1.0 - eased))

        if opacity <= 0.001 {
            opacity = 0.0
            isActive = false
            timer?.cancel()
            timer = nil
        }
    }
}
