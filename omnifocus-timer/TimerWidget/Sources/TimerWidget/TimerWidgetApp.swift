import SwiftUI
import AppKit
import Combine

@main
struct TimerWidgetApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        Settings {
            EmptyView()
        }
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow?
    private var confettiWindow: NSWindow?
    private let state = TimerState()
    private let widgetFade = FadeManager(totalDuration: 30)
    private let undoFade = FadeManager(totalDuration: 15)
    private let confetti = ConfettiState()
    private var cancellables = Set<AnyCancellable>()

    // Animation state
    private var pulseOpacity: Double = 1.0
    private var queuedGlowOpacity: Double = 0.0
    private var completingPhase: CompletingPhase = .inactive
    private var slideOutOffset: CGFloat = 0
    private var fadeInOpacity: Double = 1.0
    private var pulseTimer: AnyCancellable?
    private var completingTimer: AnyCancellable?
    private var inactivityTimer: AnyCancellable?
    private let inactivityFade = FadeManager(totalDuration: 60)
    private var hostingView: NSHostingView<WidgetView>?

    // MARK: - Pulse timing constants
    private static let runningPulseDuration: TimeInterval = 1.0
    private static let queuedSnapDuration: TimeInterval = 0.5
    private static let queuedEaseDuration: TimeInterval = 2.5
    private static let queuedTotalDuration: TimeInterval = 3.0

    func applicationDidFinishLaunching(_ notification: Notification) {
        let contentView = WidgetView(
            state: state,
            widgetFade: widgetFade,
            undoFade: undoFade,
            inactivityFade: inactivityFade,
            pulseOpacity: pulseOpacity,
            queuedGlowOpacity: queuedGlowOpacity,
            completingPhase: completingPhase,
            slideOutOffset: slideOutOffset,
            fadeInOpacity: fadeInOpacity
        )
        let hosting = NSHostingView(rootView: contentView)
        self.hostingView = hosting

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 300, height: 64),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .stationary]
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.contentView = hosting
        window.isMovableByWindowBackground = true
        window.ignoresMouseEvents = false

        positionWindow(window)
        self.window = window

        setupConfettiWindow()
        setupTrackingArea()

        // Observe state changes
        state.$widgetState
            .sink { [weak self] newState in
                guard let self = self else { return }
                let visible = self.isVisible(for: newState)
                if visible {
                    self.window?.orderFront(nil)
                } else {
                    self.window?.orderOut(nil)
                }
                self.handleStateTransition(newState)
            }
            .store(in: &cancellables)

        // Observe queue count for height changes
        state.queue.$resolvedTasks  // observe raw, visibleQueue filters
            .map { $0.count > 1 }
            .removeDuplicates()
            .sink { [weak self] hasNav in
                guard let self = self, let window = self.window else { return }
                let newHeight: CGFloat = hasNav ? 64 : 52
                var frame = window.frame
                let dy = frame.height - newHeight
                frame.size.height = newHeight
                frame.origin.y += dy
                window.setFrame(frame, display: true, animate: true)
            }
            .store(in: &cancellables)

        // When widget fade completes, transition to idle
        widgetFade.$isActive
            .dropFirst()
            .filter { !$0 }
            .sink { [weak self] _ in
                guard let self = self else { return }
                if self.state.widgetState == .lastCompleted {
                    self.state.widgetState = .idle
                }
            }
            .store(in: &cancellables)

        // When inactivity fade completes, transition to idle
        inactivityFade.$isActive
            .dropFirst()
            .filter { !$0 }
            .sink { [weak self] _ in
                guard let self = self else { return }
                if self.state.widgetState == .paused || self.state.widgetState == .queued {
                    self.state.widgetState = .idle
                }
            }
            .store(in: &cancellables)

        // Initial visibility
        if isVisible(for: state.widgetState) {
            window.orderFront(nil)
        }
    }

    // MARK: - Window Setup

    private func setupConfettiWindow() {
        guard let screen = NSScreen.main else { return }
        let confettiView = ConfettiView(confetti: confetti)
        let confettiHosting = NSHostingView(rootView: confettiView)

        // Confetti window extends below the widget
        let confWin = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 350, height: 500),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        confWin.level = .floating
        confWin.collectionBehavior = [.canJoinAllSpaces, .stationary]
        confWin.isOpaque = false
        confWin.backgroundColor = .clear
        confWin.hasShadow = false
        confWin.contentView = confettiHosting
        confWin.ignoresMouseEvents = true

        // Position confetti window centered on widget, extending below
        if let widgetWindow = window {
            let wf = widgetWindow.frame
            let x = wf.midX - 175
            let y = wf.minY - 436 // extend well below widget
            confWin.setFrameOrigin(NSPoint(x: x, y: y))
        } else {
            let visibleFrame = screen.visibleFrame
            let x = visibleFrame.maxX - 350 - 12
            let y = visibleFrame.maxY - 500 - 8
            confWin.setFrameOrigin(NSPoint(x: x, y: y))
        }

        confettiWindow = confWin
    }

    private func setupTrackingArea() {
        guard let hosting = hostingView, let window = self.window else { return }
        let tracker = MouseTrackingView(frame: hosting.bounds)
        tracker.autoresizingMask = [.width, .height]
        tracker.onEnter = { [weak self] in
            self?.widgetFade.mouseEntered()
            self?.undoFade.mouseEntered()
            self?.inactivityFade.mouseEntered()
        }
        tracker.onExit = { [weak self] in
            self?.widgetFade.mouseExited()
            self?.undoFade.mouseExited()
            self?.inactivityFade.mouseExited()
        }
        // Add tracking view as a sibling on top
        if let contentView = window.contentView {
            tracker.frame = contentView.bounds
            contentView.addSubview(tracker)
        }
    }

    // MARK: - Positioning

    private func positionWindow(_ window: NSWindow) {
        guard let screen = NSScreen.main else { return }
        let visibleFrame = screen.visibleFrame
        let windowFrame = window.frame
        let x = visibleFrame.maxX - windowFrame.width - 12
        let y = visibleFrame.maxY - windowFrame.height - 8
        window.setFrameOrigin(NSPoint(x: x, y: y))
    }

    private func isVisible(for widgetState: WidgetState) -> Bool {
        switch widgetState {
        case .idle:
            return false
        case .queued, .running, .paused, .completing, .lastCompleted:
            return true
        }
    }

    // MARK: - State Transitions

    private func handleStateTransition(_ newState: WidgetState) {
        // Stop existing pulse
        pulseTimer?.cancel()
        pulseTimer = nil
        completingTimer?.cancel()
        completingTimer = nil

        switch newState {
        case .running:
            widgetFade.stopFade()
            undoFade.stopFade()
            inactivityFade.stopFade()
            cancelInactivityTimer()
            startRunningPulse()

        case .queued:
            widgetFade.stopFade()
            undoFade.stopFade()
            inactivityFade.stopFade()
            startQueuedPulse()
            startInactivityTimer()

        case .paused:
            widgetFade.stopFade()
            undoFade.stopFade()
            inactivityFade.stopFade()
            pulseOpacity = 1.0
            queuedGlowOpacity = 0.0
            updateView()
            startInactivityTimer()

        case .completing:
            widgetFade.stopFade()
            undoFade.stopFade()
            inactivityFade.stopFade()
            cancelInactivityTimer()
            startCompletingAnimation()

        case .lastCompleted:
            pulseOpacity = 1.0
            queuedGlowOpacity = 0.0
            completingPhase = .inactive
            updateView()
            widgetFade.startFade()
            undoFade.startFade()

        case .idle:
            widgetFade.stopFade()
            undoFade.stopFade()
            pulseOpacity = 1.0
            queuedGlowOpacity = 0.0
            completingPhase = .inactive
            updateView()
        }
    }

    // MARK: - Inactivity Fade (60s for paused/queued without interaction)

    private func startInactivityTimer() {
        cancelInactivityTimer()
        inactivityTimer = Just(())
            .delay(for: .seconds(60), scheduler: DispatchQueue.main)
            .sink { [weak self] _ in
                guard let self = self else { return }
                if self.state.widgetState == .paused || self.state.widgetState == .queued {
                    self.inactivityFade.startFade()
                }
            }
    }

    private func cancelInactivityTimer() {
        inactivityTimer?.cancel()
        inactivityTimer = nil
    }

    // MARK: - Running Pulse (1s cycle, 0.92-1.0)

    private func startRunningPulse() {
        let startTime = Date()
        pulseTimer = Timer.publish(every: 1.0 / 30.0, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                guard let self = self, self.state.widgetState == .running else {
                    self?.pulseTimer?.cancel()
                    return
                }
                let elapsed = Date().timeIntervalSince(startTime)
                let phase = elapsed.truncatingRemainder(dividingBy: Self.runningPulseDuration)
                let normalized = phase / Self.runningPulseDuration
                // Sine wave: 0.92 to 1.0
                let sine = sin(normalized * .pi * 2)
                self.pulseOpacity = 0.96 + 0.04 * sine
                self.updateView()
            }
    }

    // MARK: - Queued Pulse (3s cycle: 0.5s snap to 1.0, 2.5s ease to 0.7)

    private func startQueuedPulse() {
        let startTime = Date()
        pulseTimer = Timer.publish(every: 1.0 / 30.0, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                guard let self = self, self.state.widgetState == .queued else {
                    self?.pulseTimer?.cancel()
                    return
                }
                let elapsed = Date().timeIntervalSince(startTime)
                let phase = elapsed.truncatingRemainder(dividingBy: Self.queuedTotalDuration)

                if phase < Self.queuedSnapDuration {
                    // Snap up: 0.7 -> 1.0 over 0.5s
                    let progress = phase / Self.queuedSnapDuration
                    self.pulseOpacity = 0.7 + 0.3 * progress
                    self.queuedGlowOpacity = progress
                } else {
                    // Ease out: 1.0 -> 0.7 over 2.5s
                    let easePhase = (phase - Self.queuedSnapDuration) / Self.queuedEaseDuration
                    let eased = easePhase * easePhase // ease-out quadratic
                    self.pulseOpacity = 1.0 - 0.3 * eased
                    self.queuedGlowOpacity = 1.0 - eased
                }
                self.updateView()
            }
    }

    // MARK: - Completing Animation

    private func startCompletingAnimation() {
        completingPhase = .slideOut
        slideOutOffset = 0
        fadeInOpacity = 0
        updateView()

        // Fire confetti
        if let wf = window?.frame {
            confettiWindow?.orderFront(nil)
            confetti.fire(fromRect: CGRect(x: 0, y: 0, width: wf.width, height: wf.height))
        }

        let startTime = Date()
        completingTimer = Timer.publish(every: 1.0 / 30.0, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                guard let self = self else { return }
                let elapsed = Date().timeIntervalSince(startTime)

                // Phase 2: slide out (0-3s)
                if elapsed < 3.0 {
                    self.completingPhase = .slideOut
                    let progress = min(elapsed / 3.0, 1.0)
                    // Easing acceleration (ease-in)
                    let eased = progress * progress * progress
                    self.slideOutOffset = eased * 350
                }

                // Phase 3: fade in new task (1.5-4.5s)
                if elapsed >= 1.5 && elapsed < 4.5 {
                    self.completingPhase = .fadeIn
                    self.slideOutOffset = 350 // keep old text off-screen
                    let fadeProgress = (elapsed - 1.5) / 3.0
                    // Ease-in
                    self.fadeInOpacity = fadeProgress * fadeProgress
                }

                // Phase 4: done (after 4.5s)
                if elapsed >= 4.5 {
                    self.completingPhase = .done
                    self.slideOutOffset = 0
                    self.fadeInOpacity = 1.0
                    self.completingTimer?.cancel()
                    self.completingTimer = nil

                    // Hide confetti window
                    self.confettiWindow?.orderOut(nil)
                }

                self.updateView()
            }
    }

    // MARK: - View Update

    private func updateView() {
        let contentView = WidgetView(
            state: state,
            widgetFade: widgetFade,
            undoFade: undoFade,
            inactivityFade: inactivityFade,
            pulseOpacity: pulseOpacity,
            queuedGlowOpacity: queuedGlowOpacity,
            completingPhase: completingPhase,
            slideOutOffset: slideOutOffset,
            fadeInOpacity: fadeInOpacity
        )
        hostingView?.rootView = contentView
    }
}

// MARK: - Mouse Tracking View

class MouseTrackingView: NSView {
    var onEnter: (() -> Void)?
    var onExit: (() -> Void)?

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        for area in trackingAreas {
            removeTrackingArea(area)
        }
        let area = NSTrackingArea(
            rect: bounds,
            options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
            owner: self,
            userInfo: nil
        )
        addTrackingArea(area)
    }

    override func mouseEntered(with event: NSEvent) {
        onEnter?()
    }

    override func mouseExited(with event: NSEvent) {
        onExit?()
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        // Pass through clicks to views behind
        return nil
    }
}
