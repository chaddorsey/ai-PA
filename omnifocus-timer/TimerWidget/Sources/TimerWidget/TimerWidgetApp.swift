import SwiftUI
import AppKit

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
    private let state = TimerState()
    private var stateObservation: Any?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let contentView = WidgetView(state: state)
        let hostingView = NSHostingView(rootView: contentView)

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
        window.contentView = hostingView
        window.isMovableByWindowBackground = true
        window.ignoresMouseEvents = false

        positionWindow(window)

        self.window = window

        // Observe state changes to show/hide
        stateObservation = state.$widgetState.sink { [weak self] newState in
            let visible = self?.isVisible(for: newState) ?? false
            if visible {
                self?.window?.orderFront(nil)
            } else {
                self?.window?.orderOut(nil)
            }
        }

        // Initial visibility
        if isVisible(for: state.widgetState) {
            window.orderFront(nil)
        }
    }

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
}
