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

// MARK: - Layout Constants

private enum WindowLayout {
    static let widgetWidth: CGFloat = 300
    static let widgetHeight: CGFloat = 64
    static let plusSize: CGFloat = 28
    static let margin: CGFloat = 8
    static let buffer: CGFloat = 6
    static let confettiWidth: CGFloat = 350
    static let confettiHeight: CGFloat = 500
}

class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow?
    private var plusWindow: NSWindow?
    private var confettiWindow: NSWindow?
    private var dequeueWindow: NSWindow?
    private let state = TimerState()
    private let widgetFade = FadeManager(totalDuration: 30)
    private let undoFade = FadeManager(totalDuration: 15)
    private let confetti = ConfettiState()
    private var cancellables = Set<AnyCancellable>()
    private var dequeueAnimTimer: AnyCancellable?
    private var collapsePulseTimer: AnyCancellable?

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
    private var sighupSource: DispatchSourceSignal?

    // Caps Lock LED control
    private var capsBlinkTimer: AnyCancellable?
    private var capsLedState: Bool = false

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
            contentRect: NSRect(x: 0, y: 0,
                                width: WindowLayout.widgetWidth,
                                height: WindowLayout.widgetHeight),
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
        setupPlusButton()
        setupTrackingArea()

        // Observe state changes
        state.$widgetState
            .removeDuplicates()
            .sink { [weak self] newState in
                guard let self = self else { return }
                if self.isVisible(for: newState) {
                    self.window?.alphaValue = 1.0
                    self.window?.orderFront(nil)
                } else if newState == .idle {
                    self.window?.orderOut(nil)
                }
                self.handleStateTransition(newState)
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
                    self.state.dismissedByInactivity = true
                    self.state.widgetState = .idle
                }
            }
            .store(in: &cancellables)

        // Watch for dequeue animation
        state.$isDequeuing
            .dropFirst()
            .filter { $0 }
            .sink { [weak self] _ in
                self?.playDequeueAnimation()
            }
            .store(in: &cancellables)

        // Watch for collapse pulse
        state.$collapsePulseActive
            .removeDuplicates()
            .sink { [weak self] active in
                if active {
                    self?.startCollapsePulse()
                } else {
                    self?.stopCollapsePulse()
                }
            }
            .store(in: &cancellables)

        // Handle SIGHUP as queue reload signal (sent by widget-queue.sh after mutations)
        let sighupSource = DispatchSource.makeSignalSource(signal: SIGHUP, queue: .main)
        sighupSource.setEventHandler { [weak self] in
            guard let self = self else { return }
            self.state.queue.loadQueueSync()
            self.state.dismissedByInactivity = false
            self.state.queueCount = self.state.queue.taskIds.count
            DispatchQueue.global(qos: .userInitiated).async {
                self.state.queue.resolveFromOmniFocus(bridge: self.state.bridge)
                DispatchQueue.main.async {
                    // Transition to queued after resolve completes with task names
                    if self.state.widgetState == .idle && !self.state.queue.taskIds.isEmpty {
                        self.state.transitionToQueued(index: 0)
                    } else if self.state.widgetState == .queued {
                        // Already queued — refresh the displayed task name from resolved data
                        let resolved = self.state.queue.resolvedTasks
                        let idx = min(self.state.queueIndex, resolved.count - 1)
                        if idx >= 0 && idx < resolved.count {
                            self.state.currentTaskName = resolved[idx].taskName
                            self.state.currentEstimateMin = resolved[idx].estimateMin
                        }
                    }
                }
            }
        }
        sighupSource.resume()
        signal(SIGHUP, SIG_IGN)  // Prevent default termination
        self.sighupSource = sighupSource

        // Initial visibility
        if isVisible(for: state.widgetState) {
            window.orderFront(nil)
        }

        // Reposition all windows when screen configuration changes
        NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self = self else { return }
            self.repositionAllWindows()
        }
    }

    private func repositionAllWindows() {
        guard let screen = NSScreen.main else { return }
        let visibleFrame = screen.visibleFrame

        // Reposition widget
        if let w = window {
            let plusLeftX = visibleFrame.maxX - WindowLayout.plusSize - WindowLayout.margin
            let x = plusLeftX - w.frame.width - WindowLayout.buffer
            let y = visibleFrame.maxY - w.frame.height - WindowLayout.margin
            w.setFrameOrigin(NSPoint(x: x, y: y))
        }

        // Reposition plus button
        if let p = plusWindow {
            let x = visibleFrame.maxX - WindowLayout.plusSize - WindowLayout.margin
            let y = visibleFrame.maxY - WindowLayout.plusSize - WindowLayout.margin - 2
            p.setFrameOrigin(NSPoint(x: x, y: y))
        }

        // Reposition confetti
        if let c = confettiWindow, let w = window {
            let wf = w.frame
            let x = wf.midX - WindowLayout.confettiWidth / 2
            let y = wf.minY - (WindowLayout.confettiHeight - WindowLayout.widgetHeight)
            c.setFrameOrigin(NSPoint(x: x, y: y))
        }
    }

    // MARK: - Window Setup

    private func setupConfettiWindow() {
        guard let screen = NSScreen.main else { return }
        let confettiView = ConfettiView(confetti: confetti)
        let confettiHosting = NSHostingView(rootView: confettiView)

        let confWin = NSWindow(
            contentRect: NSRect(x: 0, y: 0,
                                width: WindowLayout.confettiWidth,
                                height: WindowLayout.confettiHeight),
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
            let x = wf.midX - WindowLayout.confettiWidth / 2
            let y = wf.minY - (WindowLayout.confettiHeight - WindowLayout.widgetHeight)
            confWin.setFrameOrigin(NSPoint(x: x, y: y))
        } else {
            let visibleFrame = screen.visibleFrame
            let x = visibleFrame.maxX - WindowLayout.confettiWidth - 12
            let y = visibleFrame.maxY - WindowLayout.confettiHeight - WindowLayout.margin
            confWin.setFrameOrigin(NSPoint(x: x, y: y))
        }

        confettiWindow = confWin
    }

    private func setupPlusButton() {
        guard let screen = NSScreen.main else { return }
        let visibleFrame = screen.visibleFrame

        let plusView = PlusButtonView(
            action: { [weak self] in self?.state.queueSelectedTasks() },
            state: state
        )
        let hosting = NSHostingView(rootView: plusView)

        let plusWin = NSWindow(
            contentRect: NSRect(x: 0, y: 0,
                                width: WindowLayout.plusSize,
                                height: WindowLayout.plusSize),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        plusWin.level = .floating
        plusWin.collectionBehavior = [.canJoinAllSpaces, .stationary]
        plusWin.isOpaque = false
        plusWin.backgroundColor = .clear
        plusWin.hasShadow = false
        plusWin.contentView = hosting
        plusWin.ignoresMouseEvents = false

        // Plus button: 8px from right edge, top-aligned with widget
        // Widget top = visibleFrame.maxY - margin
        // Plus top = plusY + plusSize, so plusY = visibleFrame.maxY - margin - plusSize
        // Nudge down 2px to account for SwiftUI content inset within NSWindow
        let plusX = visibleFrame.maxX - WindowLayout.plusSize - WindowLayout.margin
        let plusY = visibleFrame.maxY - WindowLayout.plusSize - WindowLayout.margin - 2
        plusWin.setFrameOrigin(NSPoint(x: plusX, y: plusY))

        plusWin.orderFront(nil)
        plusWindow = plusWin
    }

    private func setupTrackingArea() {
        guard let hosting = hostingView, let window = self.window else { return }
        let tracker = MouseTrackingView(frame: hosting.bounds)
        tracker.autoresizingMask = [.width, .height]
        tracker.onEnter = { [weak self] in
            self?.widgetFade.mouseEntered()
            self?.undoFade.mouseEntered()
            self?.inactivityFade.mouseEntered()
            // Expand from collapsed on hover
            if self?.state.widgetState == .collapsed {
                self?.state.expandFromCollapsed()
            }
        }
        tracker.onExit = { [weak self] in
            self?.widgetFade.mouseExited()
            self?.undoFade.mouseExited()
            self?.inactivityFade.mouseExited()
        }
        if let contentView = window.contentView {
            tracker.frame = contentView.bounds
            contentView.addSubview(tracker)
        }
    }

    // MARK: - Positioning

    /// Position widget: right-justified against plus button with buffer.
    /// Both windows use visibleFrame.maxY - 8 as their top reference.
    private func positionWindow(_ window: NSWindow) {
        guard let screen = NSScreen.main else { return }
        let visibleFrame = screen.visibleFrame

        // Widget right edge = plus left edge - buffer
        let plusLeftX = visibleFrame.maxX - WindowLayout.plusSize - WindowLayout.margin
        let x = plusLeftX - WindowLayout.widgetWidth - WindowLayout.buffer
        let y = visibleFrame.maxY - WindowLayout.widgetHeight - WindowLayout.margin
        window.setFrameOrigin(NSPoint(x: x, y: y))
    }

    private func isVisible(for widgetState: WidgetState) -> Bool {
        switch widgetState {
        case .idle:
            return false
        case .queued, .running, .paused, .completing, .lastCompleted, .collapsed, .docked:
            return true
        }
    }

    private static let collapsedWidth: CGFloat = 48
    private var isCollapsedSize: Bool = false

    private func animateCollapse() {
        guard let window = self.window, let screen = NSScreen.main else { return }
        isCollapsedSize = true
        let visibleFrame = screen.visibleFrame
        let plusLeftX = visibleFrame.maxX - WindowLayout.plusSize - WindowLayout.margin
        let targetWidth = Self.collapsedWidth
        let targetX = plusLeftX - targetWidth - WindowLayout.buffer
        let targetFrame = NSRect(
            x: targetX,
            y: window.frame.origin.y,
            width: targetWidth,
            height: window.frame.height
        )
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.5
            context.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            window.animator().setFrame(targetFrame, display: true)
        })
    }

    private func animateExpand() {
        guard let window = self.window, let screen = NSScreen.main else { return }
        isCollapsedSize = false
        let visibleFrame = screen.visibleFrame
        let plusLeftX = visibleFrame.maxX - WindowLayout.plusSize - WindowLayout.margin
        let targetX = plusLeftX - WindowLayout.widgetWidth - WindowLayout.buffer
        let targetFrame = NSRect(
            x: targetX,
            y: window.frame.origin.y,
            width: WindowLayout.widgetWidth,
            height: window.frame.height
        )
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 1.0
            context.timingFunction = CAMediaTimingFunction(name: .easeOut)
            window.animator().setFrame(targetFrame, display: true)
        })
    }

    // MARK: - State Transitions

    private func handleStateTransition(_ newState: WidgetState) {
        // Stop existing animations
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
            pulseOpacity = 1.0
            queuedGlowOpacity = 0.0
            if isDocked { animateUndock() }
            else if isCollapsedSize { animateExpand() }
            updateView()

        case .queued:
            widgetFade.stopFade()
            undoFade.stopFade()
            inactivityFade.stopFade()
            startInactivityTimer()
            pulseOpacity = 1.0
            queuedGlowOpacity = 0.0
            if isDocked { animateUndock() }
            else if isCollapsedSize { animateExpand() }
            updateView()

        case .paused:
            widgetFade.stopFade()
            undoFade.stopFade()
            inactivityFade.stopFade()
            cancelInactivityTimer()
            pulseOpacity = 1.0
            queuedGlowOpacity = 0.0
            if isDocked { animateUndock() }
            else if isCollapsedSize { animateExpand() }
            updateView()

        case .collapsed:
            widgetFade.stopFade()
            undoFade.stopFade()
            inactivityFade.stopFade()
            cancelInactivityTimer()
            pulseOpacity = 1.0
            queuedGlowOpacity = 0.0
            updateView()
            animateCollapse()

        case .docked:
            widgetFade.stopFade()
            undoFade.stopFade()
            inactivityFade.stopFade()
            cancelInactivityTimer()
            pulseOpacity = 1.0
            queuedGlowOpacity = 0.0
            updateView()
            animateDock()

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
            // Dismiss immediately — confetti is the celebration, no lingering card
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
                guard let self = self, self.state.widgetState == .lastCompleted else { return }
                self.state.widgetState = .idle
            }

        case .idle:
            widgetFade.stopFade()
            undoFade.stopFade()
            pulseOpacity = 1.0
            queuedGlowOpacity = 0.0
            completingPhase = .inactive
            updateView()
        }
    }

    // MARK: - Dock Animation (vertical roll up/down)

    private static let dockTabHeight: CGFloat = WindowLayout.widgetHeight / 8  // 1/4 of previous
    private static let dockTabWidth: CGFloat = dockTabHeight * 3  // 3:1 aspect ratio
    private var isDocked: Bool = false

    private func animateDock() {
        guard let window = self.window, let screen = NSScreen.main else { return }
        isDocked = true
        let visibleFrame = screen.visibleFrame
        let currentFrame = window.frame

        // Roll up to a small tab at the top, centered on the widget's position
        let tabWidth = Self.dockTabWidth
        let tabHeight = Self.dockTabHeight
        let centerX = currentFrame.midX - tabWidth / 2
        let topY = visibleFrame.maxY - tabHeight - WindowLayout.margin

        let targetFrame = NSRect(x: centerX, y: topY, width: tabWidth, height: tabHeight)

        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.5
            context.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            window.animator().setFrame(targetFrame, display: true)
        })
    }

    private func animateUndock() {
        guard let window = self.window, let screen = NSScreen.main else { return }
        isDocked = false
        let visibleFrame = screen.visibleFrame
        let plusLeftX = visibleFrame.maxX - WindowLayout.plusSize - WindowLayout.margin
        let targetX = plusLeftX - WindowLayout.widgetWidth - WindowLayout.buffer
        let targetY = visibleFrame.maxY - WindowLayout.widgetHeight - WindowLayout.margin
        let targetFrame = NSRect(
            x: targetX, y: targetY,
            width: WindowLayout.widgetWidth, height: WindowLayout.widgetHeight
        )

        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.5
            context.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            window.animator().setFrame(targetFrame, display: true)
        })
    }

    // MARK: - Collapse Pulse (1s cycle, opacity 0.5–1.0)

    private func startCollapsePulse() {
        collapsePulseTimer?.cancel()
        let startTime = Date()
        let cycleDuration: Double = 4.0
        let minOpacity: Double = 0.75
        let range = 1.0 - minOpacity

        collapsePulseTimer = Timer.publish(every: 1.0 / 30, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                guard let self = self, self.state.collapsePulseActive else {
                    self?.collapsePulseTimer?.cancel()
                    return
                }
                let elapsed = Date().timeIntervalSince(startTime)
                let phase = elapsed.truncatingRemainder(dividingBy: cycleDuration) / cycleDuration

                // Breathing curve: raised cosine for smooth bounce off both ends
                // cos gives 1.0 at phase=0, -1.0 at phase=0.5, 1.0 at phase=1.0
                // Map to: 1.0 at top, minOpacity at bottom, smooth turnaround at both
                let cosVal = cos(phase * 2.0 * .pi)
                let opacity = minOpacity + range * (cosVal + 1.0) / 2.0

                self.pulseOpacity = opacity
                self.updateView()
            }
    }

    private func stopCollapsePulse() {
        collapsePulseTimer?.cancel()
        collapsePulseTimer = nil
        pulseOpacity = 1.0
        updateView()
    }

    // MARK: - Dequeue Animation

    private func playDequeueAnimation() {
        print("[dequeue] playDequeueAnimation called")
        guard let screen = NSScreen.main, let widgetWin = window else {
            print("[dequeue] no screen or window")
            return
        }
        guard let contentView = widgetWin.contentView else {
            print("[dequeue] no content view")
            return
        }

        let wf = widgetWin.frame
        let screenMidY = screen.frame.midY
        let fallDistance = wf.minY - screenMidY

        // Capture the widget as a bitmap snapshot for the ghost
        let bitmapRep = contentView.bitmapImageRepForCachingDisplay(in: contentView.bounds)!
        contentView.cacheDisplay(in: contentView.bounds, to: bitmapRep)
        let image = NSImage(size: contentView.bounds.size)
        image.addRepresentation(bitmapRep)

        let imageView = NSImageView(frame: NSRect(origin: .zero, size: wf.size))
        imageView.image = image
        imageView.imageScaling = .scaleAxesIndependently

        let ghostWin = NSWindow(
            contentRect: NSRect(x: wf.minX, y: wf.minY, width: wf.width, height: wf.height),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        ghostWin.level = NSWindow.Level(rawValue: NSWindow.Level.floating.rawValue + 1)
        ghostWin.collectionBehavior = [.canJoinAllSpaces, .stationary]
        ghostWin.isOpaque = false
        ghostWin.backgroundColor = .clear
        ghostWin.hasShadow = false
        ghostWin.contentView = imageView
        ghostWin.ignoresMouseEvents = true
        ghostWin.alphaValue = 0.7
        dequeueWindow = ghostWin
        print("[dequeue] ghost window created at \(wf), fallDistance=\(fallDistance)")

        // Order ghost above widget after a brief delay to ensure it's on top
        // after any state-transition-driven orderFront calls
        ghostWin.orderFront(nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
            ghostWin.orderFront(nil)
        }

        let startTime = Date()
        let fadeOutDuration: TimeInterval = 0.8
        let totalFlightDuration: TimeInterval = 0.75  // total arc time
        let hopHeight: CGFloat = 15  // pixels upward
        let peakTime: TimeInterval = 0.15  // time to reach apex (short — fast launch)
        let totalDuration = max(fadeOutDuration, totalFlightDuration)

        dequeueAnimTimer = Timer.publish(every: 1.0 / 60, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                guard let self = self, let ghost = self.dequeueWindow else { return }

                let elapsed = Date().timeIntervalSince(startTime)

                // Opacity: fade from 0.7 to 0 across fadeOutDuration
                let fadeProgress = min(elapsed / fadeOutDuration, 1.0)
                ghost.alphaValue = CGFloat(0.7 * (1.0 - fadeProgress))

                // Parabolic arc: initial velocity upward, gravity pulls down
                // y(t) = v0*t - 0.5*g*t^2 where v0 and g are chosen so:
                //   peak at t=peakTime, y(peakTime)=hopHeight
                //   y(totalFlightDuration)=fallDistance (below start)
                // v0 = hopHeight / peakTime + 0.5 * g * peakTime
                // At peak: v0 = g * peakTime → g = v0 / peakTime
                // hopHeight = v0 * peakTime - 0.5 * g * peakTime^2
                //           = 0.5 * v0 * peakTime → v0 = 2 * hopHeight / peakTime
                let v0 = 2.0 * Double(hopHeight) / peakTime
                let g = v0 / peakTime
                let t = min(elapsed, totalFlightDuration)
                let displacement = v0 * t - 0.5 * g * t * t  // positive = upward

                var frame = ghost.frame
                // In macOS coords, higher y = higher on screen
                frame.origin.y = wf.minY + CGFloat(displacement)
                ghost.setFrame(frame, display: false)

                if elapsed >= totalDuration {
                    ghost.orderOut(nil)
                    self.dequeueWindow = nil
                    self.dequeueAnimTimer?.cancel()
                    self.dequeueAnimTimer = nil
                }
            }
    }

    // MARK: - Caps Lock LED Control

    private func setCapsLock(on: Bool) {
        capsBlinkTimer?.cancel()
        capsBlinkTimer = nil

        let current = getCapsLockState()
        if current != on {
            toggleCapsLockKey()
        }
        capsLedState = on
    }

    private func startCapsLockBlink() {
        capsBlinkTimer?.cancel()
        if !getCapsLockState() {
            toggleCapsLockKey()
        }
        capsLedState = true

        capsBlinkTimer = Timer.publish(every: 1.0, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                guard let self = self, self.state.widgetState == .paused else {
                    self?.capsBlinkTimer?.cancel()
                    self?.capsBlinkTimer = nil
                    return
                }
                self.toggleCapsLockKey()
                self.capsLedState.toggle()
            }
    }

    private func getCapsLockState() -> Bool {
        let flags = CGEventSource.flagsState(.combinedSessionState)
        return flags.contains(.maskAlphaShift)
    }

    private func toggleCapsLockKey() {
        let keyDown = CGEvent(keyboardEventSource: nil, virtualKey: 0x39, keyDown: true)
        let keyUp = CGEvent(keyboardEventSource: nil, virtualKey: 0x39, keyDown: false)
        keyDown?.post(tap: .cghidEventTap)
        keyUp?.post(tap: .cghidEventTap)
    }

    // MARK: - Inactivity Fade (60s for queued without interaction)

    private func startInactivityTimer() {
        cancelInactivityTimer()
        inactivityTimer = Just(())
            .delay(for: .seconds(60), scheduler: DispatchQueue.main)
            .sink { [weak self] _ in
                guard let self = self else { return }
                if self.state.widgetState == .queued {
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
                    let progress = phase / Self.queuedSnapDuration
                    self.pulseOpacity = 0.7 + 0.3 * progress
                    self.queuedGlowOpacity = progress
                } else {
                    let easePhase = (phase - Self.queuedSnapDuration) / Self.queuedEaseDuration
                    let eased = easePhase * easePhase
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

                // Phase 1: slide out (0-3s)
                if elapsed < 3.0 {
                    self.completingPhase = .slideOut
                    let progress = min(elapsed / 3.0, 1.0)
                    let eased = progress * progress * progress
                    self.slideOutOffset = eased * 350
                }

                // Phase 2: fade in new task (1.5-4.5s)
                if elapsed >= 1.5 && elapsed < 4.5 {
                    self.completingPhase = .fadeIn
                    self.slideOutOffset = 350
                    let fadeProgress = (elapsed - 1.5) / 3.0
                    self.fadeInOpacity = fadeProgress * fadeProgress
                }

                // Phase 3: done (after 4.5s)
                if elapsed >= 4.5 {
                    self.completingPhase = .done
                    self.slideOutOffset = 0
                    self.fadeInOpacity = 1.0
                    self.completingTimer?.cancel()
                    self.completingTimer = nil

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
        return nil
    }
}
