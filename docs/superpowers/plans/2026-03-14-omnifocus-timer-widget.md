# OmniFocus Timer Widget Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a floating macOS widget that shows the active OmniFocus timer, provides play/pause/done controls with confetti completion animations, and accepts a task queue from Letta/Rover.

**Architecture:** SwiftUI app with AppKit window management. Polls the OmniFocus timer plugin via osascript every 2 seconds. Reads a task queue from a local JSON file written by Letta/Rover. No external dependencies.

**Tech Stack:** Swift, SwiftUI, AppKit (NSWindow), macOS 13+

**Spec:** `docs/superpowers/specs/2026-03-14-omnifocus-timer-widget-design.md`

---

## File Structure

All files live in `omnifocus-timer/TimerWidget/`:

| File | Responsibility |
|------|---------------|
| `Package.swift` | Swift Package Manager manifest |
| `Sources/TimerWidget/TimerWidgetApp.swift` | App entry point, NSWindow creation, floating window setup |
| `Sources/TimerWidget/TimerState.swift` | ObservableObject: widget state machine, task cache, animation timers, fade/undo state |
| `Sources/TimerWidget/WidgetView.swift` | Main SwiftUI view: state-dependent layout, buttons, task name, estimate, navigation dots |
| `Sources/TimerWidget/OmniFocusBridge.swift` | osascript execution: poll timer status, send commands (start/pause/resume/stop/complete/undo) |
| `Sources/TimerWidget/QueueManager.swift` | File watcher for `~/.omnifocus-timer-widget/queue.json`, queue diffing, task queue model |
| `Sources/TimerWidget/ConfettiView.swift` | Particle system for completion celebration confetti |
| `Sources/TimerWidget/FadeManager.swift` | Reusable fade-out logic with hover interruption (used by widget fade and undo fade) |
| `Resources/Info.plist` | LSUIElement=true, bundle identifier |

---

## Chunk 1: Foundation — Window, State Machine, and Polling

### Task 1: Swift Package Scaffold

**Files:**
- Create: `omnifocus-timer/TimerWidget/Package.swift`
- Create: `omnifocus-timer/TimerWidget/Sources/TimerWidget/TimerWidgetApp.swift`
- Create: `omnifocus-timer/TimerWidget/Resources/Info.plist`

- [ ] **Step 1: Create Package.swift**

```swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "TimerWidget",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "TimerWidget",
            resources: [.process("../../Resources")]
        ),
    ]
)
```

- [ ] **Step 2: Create Info.plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.dorsey.omnifocus-timer-widget</string>
    <key>CFBundleName</key>
    <string>TimerWidget</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
```

- [ ] **Step 3: Create minimal TimerWidgetApp.swift with floating window**

```swift
import SwiftUI
import AppKit

@main
struct TimerWidgetApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        Settings { EmptyView() }
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var state = TimerState()

    func applicationDidFinishLaunching(_ notification: Notification) {
        let contentView = WidgetView(state: state)

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 300, height: 64),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .stationary]
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.contentView = NSHostingView(rootView: contentView)

        positionWindow()
        // Start hidden
        window.orderOut(nil)
    }

    func positionWindow() {
        guard let screen = NSScreen.main else { return }
        let screenFrame = screen.visibleFrame
        let windowFrame = window.frame
        let x = screenFrame.maxX - windowFrame.width - 8
        let y = screenFrame.maxY - windowFrame.height - 4
        window.setFrameOrigin(NSPoint(x: x, y: y))
    }
}
```

- [ ] **Step 4: Create placeholder files so it compiles**

Create minimal `TimerState.swift`:
```swift
import SwiftUI

enum WidgetState {
    case idle
    case queued
    case running
    case paused
    case completing
    case lastCompleted
}

struct QueuedTask: Identifiable, Codable, Equatable {
    let id: String  // taskId
    let taskName: String
    let estimateMin: Int

    enum CodingKeys: String, CodingKey {
        case id = "taskId"
        case taskName
        case estimateMin
    }
}

class TimerState: ObservableObject {
    @Published var widgetState: WidgetState = .idle
    @Published var currentTaskId: String?
    @Published var currentTaskName: String = ""
    @Published var currentEstimateMin: Int = 0
    @Published var queue: [QueuedTask] = []
    @Published var queueIndex: Int = 0
    @Published var cachedTaskId: String?
    @Published var cachedTaskName: String = ""
    @Published var showUndo: Bool = false
    @Published var undoTaskId: String?
}
```

Create minimal `WidgetView.swift`:
```swift
import SwiftUI

struct WidgetView: View {
    @ObservedObject var state: TimerState

    var body: some View {
        Text("Timer Widget")
            .frame(width: 300, height: 64)
    }
}
```

- [ ] **Step 5: Verify it builds and runs**

```bash
cd omnifocus-timer/TimerWidget
swift build
swift run TimerWidget
```

Expected: App launches with no visible window (LSUIElement), no dock icon. Kill with Ctrl+C.

- [ ] **Step 6: Commit**

```bash
git add omnifocus-timer/TimerWidget/
git commit -m "feat(timer-widget): scaffold Swift package with floating window"
```

---

### Task 2: OmniFocus Bridge — Polling and Commands

**Files:**
- Create: `omnifocus-timer/TimerWidget/Sources/TimerWidget/OmniFocusBridge.swift`

- [ ] **Step 1: Write the OmniFocus bridge**

```swift
import Foundation

struct TimerStatusResponse: Codable {
    let status: String          // "running", "paused", "idle"
    let taskId: String?
    let taskName: String?
    let projectName: String?
    let elapsedFormatted: String?
    let sessionCount: Int?
    let originalEstimate: Int?  // minutes
}

class OmniFocusBridge {
    static let shared = OmniFocusBridge()

    private let pluginId = "com.dorsey.omnifocus-timer"
    private let libraryId = "timerLib"

    /// Poll timer status. Returns nil if OmniFocus is unavailable.
    func getTimerStatus() -> TimerStatusResponse? {
        let js = "JSON.stringify(PlugIn.find('\(pluginId)').library('\(libraryId)').getTimerStatus())"
        guard let result = evaluateJS(js) else { return nil }
        guard let data = result.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(TimerStatusResponse.self, from: data)
    }

    func startTimer(taskId: String) {
        let js = "PlugIn.find('\(pluginId)').library('\(libraryId)').startTimerOnTask('\(escapeJS(taskId))')"
        _ = evaluateJS(js)
    }

    func pauseTimer() {
        let js = "PlugIn.find('\(pluginId)').library('\(libraryId)').pauseTimer()"
        _ = evaluateJS(js)
    }

    func resumeTimer() {
        let js = "PlugIn.find('\(pluginId)').library('\(libraryId)').resumeTimer()"
        _ = evaluateJS(js)
    }

    func completeTask(taskId: String) {
        // Stop timer and mark task complete
        let js = """
        var lib = PlugIn.find('\(pluginId)').library('\(libraryId)');
        lib.stopTimer();
        var task = Task.byIdentifier('\(escapeJS(taskId))');
        if (task) task.markComplete();
        JSON.stringify({status: 'completed'})
        """
        _ = evaluateJS(js)
    }

    func undoComplete(taskId: String) {
        let js = """
        var task = Task.byIdentifier('\(escapeJS(taskId))');
        if (task) task.markIncomplete();
        JSON.stringify({status: 'uncompleted'})
        """
        _ = evaluateJS(js)
    }

    func navigateToTask(taskId: String) {
        if let url = URL(string: "omnifocus:///task/\(taskId)") {
            NSWorkspace.shared.open(url)
        }
    }

    // MARK: - Private

    private func escapeJS(_ s: String) -> String {
        s.replacingOccurrences(of: "\\", with: "\\\\")
         .replacingOccurrences(of: "'", with: "\\'")
    }

    private func evaluateJS(_ js: String) -> String? {
        // Write osascript to temp file to avoid quoting issues
        let escaped = js.replacingOccurrences(of: "\"", with: "\\\"")
        let appleScript = """
        tell application "OmniFocus" to evaluate javascript "\(escaped)"
        """

        let tempFile = NSTemporaryDirectory() + "timer-widget-\(ProcessInfo.processInfo.processIdentifier).applescript"
        do {
            try appleScript.write(toFile: tempFile, atomically: true, encoding: .utf8)
        } catch {
            return nil
        }
        defer { try? FileManager.default.removeItem(atPath: tempFile) }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = [tempFile]

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = Pipe() // discard stderr

        do {
            try process.run()
            process.waitUntilExit()

            guard process.terminationStatus == 0 else { return nil }

            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            var result = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)

            // osascript may double-wrap in quotes
            if let r = result, r.hasPrefix("\"") && r.hasSuffix("\"") {
                result = String(r.dropFirst().dropLast())
                    .replacingOccurrences(of: "\\\"", with: "\"")
                    .replacingOccurrences(of: "\\\\", with: "\\")
            }
            return result
        } catch {
            return nil
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add omnifocus-timer/TimerWidget/Sources/TimerWidget/OmniFocusBridge.swift
git commit -m "feat(timer-widget): add OmniFocus bridge for polling and commands"
```

---

### Task 3: Queue Manager — File Watching

**Files:**
- Create: `omnifocus-timer/TimerWidget/Sources/TimerWidget/QueueManager.swift`

- [ ] **Step 1: Write the queue manager**

```swift
import Foundation
import Combine

struct QueueFile: Codable {
    let tasks: [QueuedTask]
}

class QueueManager: ObservableObject {
    @Published var tasks: [QueuedTask] = []

    private let queueDir: String
    private let queuePath: String
    private var fileDescriptor: Int32 = -1
    private var dispatchSource: DispatchSourceFileSystemObject?

    init() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        queueDir = "\(home)/.omnifocus-timer-widget"
        queuePath = "\(queueDir)/queue.json"
        ensureDirectory()
        loadQueue()
        startWatching()
    }

    deinit {
        stopWatching()
    }

    func removeTask(at index: Int) {
        guard index >= 0 && index < tasks.count else { return }
        tasks.remove(at: index)
        saveQueue()
    }

    func removeTask(id: String) {
        tasks.removeAll { $0.id == id }
        saveQueue()
    }

    // MARK: - Private

    private func ensureDirectory() {
        try? FileManager.default.createDirectory(
            atPath: queueDir,
            withIntermediateDirectories: true
        )
        if !FileManager.default.fileExists(atPath: queuePath) {
            try? "{\"tasks\":[]}".write(toFile: queuePath, atomically: true, encoding: .utf8)
        }
    }

    func loadQueue() {
        guard let data = FileManager.default.contents(atPath: queuePath),
              let queueFile = try? JSONDecoder().decode(QueueFile.self, from: data) else {
            return
        }
        DispatchQueue.main.async {
            self.tasks = queueFile.tasks
        }
    }

    private func saveQueue() {
        let queueFile = QueueFile(tasks: tasks)
        guard let data = try? JSONEncoder().encode(queueFile) else { return }
        try? data.write(to: URL(fileURLWithPath: queuePath))
    }

    private func startWatching() {
        fileDescriptor = open(queuePath, O_EVTONLY)
        guard fileDescriptor >= 0 else { return }

        dispatchSource = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: fileDescriptor,
            eventMask: [.write, .rename],
            queue: .main
        )
        dispatchSource?.setEventHandler { [weak self] in
            self?.loadQueue()
        }
        dispatchSource?.setCancelHandler { [weak self] in
            if let fd = self?.fileDescriptor, fd >= 0 {
                close(fd)
            }
        }
        dispatchSource?.resume()
    }

    private func stopWatching() {
        dispatchSource?.cancel()
        dispatchSource = nil
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add omnifocus-timer/TimerWidget/Sources/TimerWidget/QueueManager.swift
git commit -m "feat(timer-widget): add queue manager with file watching"
```

---

### Task 4: Timer State Machine — Polling Loop and State Transitions

**Files:**
- Modify: `omnifocus-timer/TimerWidget/Sources/TimerWidget/TimerState.swift`

- [ ] **Step 1: Implement the full state machine with polling**

Replace the placeholder `TimerState.swift` with the full implementation:

```swift
import SwiftUI
import Combine

enum WidgetState: Equatable {
    case idle
    case queued
    case running
    case paused
    case completing
    case lastCompleted
}

struct QueuedTask: Identifiable, Codable, Equatable {
    let id: String
    let taskName: String
    let estimateMin: Int

    enum CodingKeys: String, CodingKey {
        case id = "taskId"
        case taskName
        case estimateMin
    }
}

class TimerState: ObservableObject {
    @Published var widgetState: WidgetState = .idle
    @Published var currentTaskId: String?
    @Published var currentTaskName: String = ""
    @Published var currentEstimateMin: Int = 0
    @Published var queueIndex: Int = 0

    // Undo
    @Published var showUndo: Bool = false
    @Published var undoTaskId: String?
    @Published var undoTaskName: String = ""

    // Cache for stopped state
    var cachedTaskId: String?
    var cachedTaskName: String = ""

    // Previous poll status for idle transition detection
    var previousPollStatus: String = "idle"

    let bridge = OmniFocusBridge.shared
    let queueManager = QueueManager()

    private var pollTimer: AnyCancellable?

    init() {
        startPolling()
    }

    func startPolling() {
        poll() // immediate first poll
        schedulePoll()
    }

    private func schedulePoll() {
        pollTimer = Just(())
            .delay(for: .seconds(2), scheduler: DispatchQueue.global(qos: .userInitiated))
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                self?.poll()
                self?.schedulePoll()
            }
    }

    private func poll() {
        // Also reload queue
        queueManager.loadQueue()

        guard let status = bridge.getTimerStatus() else {
            // OmniFocus unavailable — show queue if we have one
            if !queueManager.tasks.isEmpty && widgetState == .idle {
                transitionToQueued()
            }
            previousPollStatus = "idle"
            return
        }

        switch status.status {
        case "running":
            if widgetState != .completing {
                currentTaskId = status.taskId
                currentTaskName = status.taskName ?? ""
                currentEstimateMin = status.originalEstimate ?? 0
                cachedTaskId = status.taskId
                cachedTaskName = status.taskName ?? ""
                if widgetState != .running {
                    widgetState = .running
                }
            }

        case "paused":
            if widgetState != .completing {
                currentTaskId = status.taskId
                currentTaskName = status.taskName ?? ""
                currentEstimateMin = status.originalEstimate ?? 0
                cachedTaskId = status.taskId
                cachedTaskName = status.taskName ?? ""
                if widgetState != .paused {
                    widgetState = .paused
                }
            }

        default: // "idle"
            if previousPollStatus == "running" || previousPollStatus == "paused" {
                // Timer just stopped — transition based on queue
                if widgetState != .completing && widgetState != .lastCompleted {
                    if !queueManager.tasks.isEmpty {
                        transitionToQueued()
                    } else {
                        widgetState = .lastCompleted
                    }
                }
            } else if widgetState == .idle && !queueManager.tasks.isEmpty {
                transitionToQueued()
            }
        }

        previousPollStatus = status.status
    }

    func transitionToQueued() {
        queueIndex = 0
        if let task = queueManager.tasks.first {
            currentTaskId = task.id
            currentTaskName = task.taskName
            currentEstimateMin = task.estimateMin
        }
        widgetState = .queued
    }

    // MARK: - Actions

    func playPressed() {
        guard let taskId = currentTaskId else { return }
        bridge.startTimer(taskId: taskId)
        // Remove from queue if it was queued
        queueManager.removeTask(id: taskId)
        widgetState = .running
    }

    func pausePressed() {
        bridge.pauseTimer()
        widgetState = .paused
    }

    func donePressed() {
        guard let taskId = currentTaskId else { return }
        undoTaskId = taskId
        undoTaskName = currentTaskName
        bridge.completeTask(taskId: taskId)
        queueManager.removeTask(id: taskId)

        if queueManager.tasks.isEmpty {
            widgetState = .lastCompleted
        } else {
            widgetState = .completing
        }
        showUndo = true
    }

    func undoPressed() {
        guard let taskId = undoTaskId else { return }
        bridge.undoComplete(taskId: taskId)
        currentTaskId = taskId
        currentTaskName = undoTaskName
        showUndo = false
        widgetState = .paused
    }

    func navigateQueue(direction: Int) {
        // If running, auto-pause first
        if widgetState == .running {
            bridge.pauseTimer()
        }

        let newIndex = queueIndex + direction
        guard newIndex >= 0 && newIndex < queueManager.tasks.count else { return }
        queueIndex = newIndex

        let task = queueManager.tasks[newIndex]
        currentTaskId = task.id
        currentTaskName = task.taskName
        currentEstimateMin = task.estimateMin
        widgetState = .queued
    }

    func taskNameClicked() {
        guard let taskId = currentTaskId else { return }
        bridge.navigateToTask(taskId: taskId)
    }

    // After completing transition animation, show next queued task
    func completionAnimationFinished() {
        if !queueManager.tasks.isEmpty {
            transitionToQueued()
        } else {
            widgetState = .idle
        }
    }

    var isVisible: Bool {
        widgetState != .idle
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add omnifocus-timer/TimerWidget/Sources/TimerWidget/TimerState.swift
git commit -m "feat(timer-widget): implement state machine with polling and queue integration"
```

---

## Chunk 2: UI — Widget View, Animations, and Confetti

### Task 5: Widget View — Main Layout

**Files:**
- Modify: `omnifocus-timer/TimerWidget/Sources/TimerWidget/WidgetView.swift`

- [ ] **Step 1: Implement the full widget view**

```swift
import SwiftUI

struct WidgetView: View {
    @ObservedObject var state: TimerState

    var body: some View {
        ZStack {
            if state.isVisible {
                widgetContent
                    .background(backgroundColor)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .shadow(color: glowColor, radius: glowRadius)
                    .opacity(widgetOpacity)
            }
        }
        .frame(width: 300, height: widgetHeight)
    }

    @ViewBuilder
    private var widgetContent: some View {
        HStack(spacing: 0) {
            // Left: Buttons
            buttonColumn
                .frame(width: 36)

            // Center: Task name
            taskNameView
                .frame(maxWidth: .infinity, alignment: .leading)
                .onTapGesture { state.taskNameClicked() }

            // Right: Estimate + Navigation
            rightColumn
                .frame(width: 56)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
    }

    // MARK: - Buttons

    @ViewBuilder
    private var buttonColumn: some View {
        VStack(spacing: 4) {
            // Top button: Play or Pause
            if state.widgetState == .running {
                iconButton(systemName: "pause.fill") { state.pausePressed() }
            } else {
                iconButton(systemName: "play.fill") { state.playPressed() }
                    .overlay(
                        state.widgetState == .queued
                            ? playGlow : nil
                    )
            }

            // Bottom button: Done checkmark (only when running or paused with active task)
            if state.widgetState == .running || state.widgetState == .paused {
                doneButton
            }
        }
    }

    private var doneButton: some View {
        Button(action: { state.donePressed() }) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(Color(red: 0.15, green: 0.55, blue: 0.15))
        }
        .buttonStyle(.plain)
        .frame(width: 24, height: 24)
        .contentShape(Rectangle())
        .onHover { hovering in
            // Hover highlight handled via overlay
        }
    }

    @ViewBuilder
    private var playGlow: some View {
        Circle()
            .fill(Color.green.opacity(0.4))
            .frame(width: 28, height: 28)
            .blur(radius: 6)
    }

    private func iconButton(systemName: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 14))
                .foregroundColor(.black)
                .frame(width: 24, height: 24)
        }
        .buttonStyle(WidgetButtonStyle())
    }

    // MARK: - Task Name

    private var taskNameView: some View {
        Text(state.currentTaskName)
            .font(.system(size: 11, weight: .bold))
            .foregroundColor(.black)
            .lineLimit(2)
            .truncationMode(.tail)
            .padding(.leading, 4)
    }

    // MARK: - Right Column

    @ViewBuilder
    private var rightColumn: some View {
        VStack(spacing: 2) {
            // Estimate
            if state.currentEstimateMin > 0 {
                estimateView
            }

            // Navigation dots
            if state.queueManager.tasks.count > 1 {
                navigationView
            }
        }
    }

    private var estimateView: some View {
        VStack(spacing: 0) {
            let (number, unit) = formatEstimate(state.currentEstimateMin)
            Text(number)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.black)
            Text(unit)
                .font(.system(size: 8))
                .foregroundColor(.black.opacity(0.7))
        }
    }

    @ViewBuilder
    private var navigationView: some View {
        HStack(spacing: 4) {
            if state.queueIndex > 0 {
                iconButton(systemName: "chevron.left") {
                    state.navigateQueue(direction: -1)
                }
                .font(.system(size: 8))
            }

            ForEach(0..<state.queueManager.tasks.count, id: \.self) { i in
                Circle()
                    .fill(i == state.queueIndex ? Color.black : Color.black.opacity(0.3))
                    .frame(width: 5, height: 5)
                    .transition(.opacity.combined(with: .scale))
            }

            if state.queueIndex < state.queueManager.tasks.count - 1 {
                iconButton(systemName: "chevron.right") {
                    state.navigateQueue(direction: 1)
                }
                .font(.system(size: 8))
            }
        }
    }

    // MARK: - Computed Properties

    private var backgroundColor: Color {
        switch state.widgetState {
        case .idle: return .clear
        case .queued: return Color(red: 0.66, green: 0.9, blue: 0.81) // #A8E6CF
        case .running, .completing, .lastCompleted: return Color(red: 0.2, green: 0.78, blue: 0.35) // #34C759
        case .paused: return Color(red: 0.56, green: 0.56, blue: 0.58) // #8E8E93
        }
    }

    private var glowColor: Color {
        state.widgetState == .running ? Color.green.opacity(0.3) : .clear
    }

    private var glowRadius: CGFloat {
        state.widgetState == .running ? 8 : 0
    }

    private var widgetOpacity: Double {
        1.0 // Managed externally by FadeManager
    }

    private var widgetHeight: CGFloat {
        state.queueManager.tasks.count > 1 ? 64 : 52
    }

    private func formatEstimate(_ minutes: Int) -> (String, String) {
        if minutes >= 60 {
            let hours = minutes / 60
            return ("\(hours)", minutes % 60 == 0 ? "hr" : "hr")
        }
        return ("\(minutes)", "min")
    }
}

struct WidgetButtonStyle: ButtonStyle {
    @State private var isHovered = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.white.opacity(isHovered ? 0.15 : 0))
            )
            .onHover { isHovered = $0 }
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add omnifocus-timer/TimerWidget/Sources/TimerWidget/WidgetView.swift
git commit -m "feat(timer-widget): implement main widget view with buttons, estimate, and navigation"
```

---

### Task 6: Fade Manager — Reusable Fade-Out with Hover

**Files:**
- Create: `omnifocus-timer/TimerWidget/Sources/TimerWidget/FadeManager.swift`

- [ ] **Step 1: Implement the fade manager**

```swift
import SwiftUI
import Combine

/// Manages a timed fade-out with hover interruption behavior.
/// Used for both the widget's 30s fade-out and the undo button's 15s fade.
class FadeManager: ObservableObject {
    @Published var opacity: Double = 1.0
    @Published var isActive: Bool = false

    let totalDuration: TimeInterval
    private var startTime: Date?
    private var pausedOpacity: Double?
    private var hoverStartTime: Date?
    private var displayLink: AnyCancellable?

    init(duration: TimeInterval) {
        self.totalDuration = duration
    }

    func startFade() {
        isActive = true
        opacity = 1.0
        startTime = Date()
        pausedOpacity = nil

        displayLink = Timer.publish(every: 1.0 / 30, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                self?.tick()
            }
    }

    func stopFade() {
        isActive = false
        opacity = 1.0
        displayLink = nil
        startTime = nil
        pausedOpacity = nil
    }

    func mouseEntered() {
        guard isActive else { return }
        pausedOpacity = opacity
        opacity = 1.0
        hoverStartTime = Date()
        displayLink = nil // pause the fade
    }

    func mouseExited() {
        guard isActive, let hoverStart = hoverStartTime else { return }
        let hoverDuration = Date().timeIntervalSince(hoverStart)
        hoverStartTime = nil

        if hoverDuration >= 5.0 {
            // Reset fade timer
            startTime = Date()
            pausedOpacity = nil
            opacity = 1.0
        } else {
            // Resume from where we were
            opacity = pausedOpacity ?? opacity
            // Adjust startTime so the fade continues from the paused point
            let elapsed = (1.0 - (pausedOpacity ?? 1.0)) * totalDuration
            startTime = Date().addingTimeInterval(-elapsed)
            pausedOpacity = nil
        }

        // Restart tick
        displayLink = Timer.publish(every: 1.0 / 30, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                self?.tick()
            }
    }

    private func tick() {
        guard let start = startTime else { return }
        let elapsed = Date().timeIntervalSince(start)
        let progress = min(elapsed / totalDuration, 1.0)

        // Ease-in-ease-out curve
        let eased = progress < 0.5
            ? 2 * progress * progress
            : 1 - pow(-2 * progress + 2, 2) / 2

        opacity = 1.0 - eased

        if progress >= 1.0 {
            opacity = 0
            isActive = false
            displayLink = nil
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add omnifocus-timer/TimerWidget/Sources/TimerWidget/FadeManager.swift
git commit -m "feat(timer-widget): add FadeManager with hover interruption behavior"
```

---

### Task 7: Confetti View — Completion Celebration

**Files:**
- Create: `omnifocus-timer/TimerWidget/Sources/TimerWidget/ConfettiView.swift`

- [ ] **Step 1: Implement the confetti particle system**

```swift
import SwiftUI

struct ConfettiParticle: Identifiable {
    let id = UUID()
    var x: CGFloat
    var y: CGFloat
    var velocityX: CGFloat
    var velocityY: CGFloat  // negative = upward
    var color: Color
    var size: CGFloat
    var rotation: Double
    var rotationSpeed: Double
    var opacity: Double = 1.0
}

struct ConfettiView: View {
    @Binding var isActive: Bool
    let originY: CGFloat  // widget bottom edge y position

    @State private var particles: [ConfettiParticle] = []
    @State private var timer: Timer?

    let screenMidY: CGFloat = (NSScreen.main?.frame.height ?? 800) / 2
    let gravity: CGFloat = 400 // pixels/s^2

    var body: some View {
        Canvas { context, size in
            for particle in particles {
                context.opacity = particle.opacity
                context.translateBy(x: particle.x, y: particle.y)
                context.rotate(by: .degrees(particle.rotation))
                context.fill(
                    Rectangle().path(in: CGRect(
                        x: -particle.size / 2,
                        y: -particle.size / 2,
                        width: particle.size,
                        height: particle.size
                    )),
                    with: .color(particle.color)
                )
                context.rotate(by: .degrees(-particle.rotation))
                context.translateBy(x: -particle.x, y: -particle.y)
            }
        }
        .allowsHitTesting(false)
        .onChange(of: isActive) { _, active in
            if active { spawnParticles() }
        }
    }

    private func spawnParticles() {
        let colors: [Color] = [.yellow, .orange, .pink, .purple, .blue, .green, .red]
        var newParticles: [ConfettiParticle] = []

        for _ in 0..<40 {
            let angle = Double.random(in: -Double.pi * 0.8 ... -Double.pi * 0.2) // mostly downward with some upward
            let speed = CGFloat.random(in: 200...500)
            newParticles.append(ConfettiParticle(
                x: CGFloat.random(in: 100...200), // centered on widget
                y: 0, // top of confetti overlay (near widget)
                velocityX: cos(angle) * speed,
                velocityY: sin(angle) * speed,
                color: colors.randomElement()!,
                size: CGFloat.random(in: 4...8),
                rotation: Double.random(in: 0...360),
                rotationSpeed: Double.random(in: -720...720)
            ))
        }

        particles = newParticles

        let startTime = Date()
        let dt: TimeInterval = 1.0 / 60

        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: dt, repeats: true) { t in
            let elapsed = Date().timeIntervalSince(startTime)

            if elapsed > 2.5 {
                t.invalidate()
                particles = []
                isActive = false
                return
            }

            for i in particles.indices {
                particles[i].velocityY += gravity * CGFloat(dt)
                particles[i].x += particles[i].velocityX * CGFloat(dt)
                particles[i].y += particles[i].velocityY * CGFloat(dt)
                particles[i].rotation += particles[i].rotationSpeed * dt

                // Fade based on distance from origin
                let fallDistance = particles[i].y
                let maxDistance = screenMidY
                particles[i].opacity = max(0, 1.0 - Double(fallDistance / maxDistance))
            }
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add omnifocus-timer/TimerWidget/Sources/TimerWidget/ConfettiView.swift
git commit -m "feat(timer-widget): add confetti particle system for completion celebration"
```

---

### Task 8: Wire Everything Together — AppDelegate, Window Visibility, Animations

**Files:**
- Modify: `omnifocus-timer/TimerWidget/Sources/TimerWidget/TimerWidgetApp.swift`
- Modify: `omnifocus-timer/TimerWidget/Sources/TimerWidget/WidgetView.swift`

- [ ] **Step 1: Update AppDelegate to manage window visibility and confetti overlay**

Update `TimerWidgetApp.swift` to:
- Show/hide the main window based on `state.isVisible`
- Create a transparent confetti overlay window below the widget
- Manage the `FadeManager` for the lastCompleted state
- Manage the undo fade timer
- Wire pulse animations (running: 1s subtle, queued: 3s dramatic)
- Observe `state.widgetState` changes to trigger/stop animations

The AppDelegate should:
- Watch `state.$widgetState` with Combine
- When `.running`: start 1s pulse animation (opacity 0.92-1.0)
- When `.queued`: start 3s pulse animation (opacity 0.7-1.0 with 0.5s snap-up, 2.5s ease-down)
- When `.paused`: stop all animations, set opacity to 1.0
- When `.completing`: trigger confetti, manage completion animation phases
- When `.lastCompleted`: start 30s fade via FadeManager
- When `.idle`: hide window
- Handle mouse tracking for fade hover behavior

- [ ] **Step 2: Update WidgetView to integrate undo button and completion transitions**

Add:
- Small undo button in upper-left corner (when `state.showUndo` and post-completion)
- Task text slide-out animation (when completing)
- New task text fade-in animation (staggered 1.5s)
- Navigation dot removal animation for completed task

- [ ] **Step 3: Build and test**

```bash
cd omnifocus-timer/TimerWidget
swift build
```

Fix any compilation errors.

- [ ] **Step 4: Commit**

```bash
git add omnifocus-timer/TimerWidget/Sources/TimerWidget/
git commit -m "feat(timer-widget): wire window management, animations, and confetti overlay"
```

---

## Chunk 3: Integration and Polish

### Task 9: Update Toggle Script for Completion

**Files:**
- Modify: `omnifocus-timer/toggle-timer.sh`

- [ ] **Step 1: Update toggle script to complete tasks instead of just stopping**

When a timer is running, Caps Lock should mark the task complete (not just stop it):

```bash
#!/bin/bash
# Toggle OmniFocus timer via Caps Lock

export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export PYTHONPATH="/Users/chaddorsey/Dropbox/dev/omnifocus-cli/src:$PYTHONPATH"

STATUS=$(python3 -c "from omnifocus_cli.cli import cli; cli()" --format json timer status 2>/dev/null)
STATE=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','idle'))" 2>/dev/null)
TASK_ID=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('taskId',''))" 2>/dev/null)

if [ "$STATE" = "running" ]; then
  # Complete the task: stop timer + mark complete
  python3 -c "from omnifocus_cli.cli import cli; cli()" --format json timer stop 2>/dev/null
  # Mark complete via osascript
  osascript -e "tell application \"OmniFocus\" to evaluate javascript \"var t=Task.byIdentifier('$TASK_ID');if(t)t.markComplete();'done'\"" 2>/dev/null
elif [ "$STATE" = "paused" ]; then
  # Resume the paused task
  python3 -c "from omnifocus_cli.cli import cli; cli()" --format json timer resume 2>/dev/null
else
  # No timer — start on the selected task in OmniFocus
  TASK_ID=$(osascript -e 'tell application "OmniFocus" to evaluate javascript "document.windows[0].selection.tasks[0].id.primaryKey"' 2>/dev/null)
  if [ -n "$TASK_ID" ]; then
    python3 -c "from omnifocus_cli.cli import cli; cli()" --format json timer start "$TASK_ID" 2>/dev/null
  fi
fi
```

- [ ] **Step 2: Commit**

```bash
git add omnifocus-timer/toggle-timer.sh
git commit -m "feat(omnifocus-timer): update Caps Lock toggle to complete tasks"
```

---

### Task 10: Manual Testing

**Files:** None

- [ ] **Step 1: Build and run the widget**

```bash
cd omnifocus-timer/TimerWidget
swift build
swift run TimerWidget &
```

- [ ] **Step 2: Test queued state**

Write a test queue file:
```bash
mkdir -p ~/.omnifocus-timer-widget
echo '{"tasks":[{"taskId":"test1","taskName":"Test task for widget","estimateMin":15},{"taskId":"test2","taskName":"Second test task","estimateMin":5}]}' > ~/.omnifocus-timer-widget/queue.json
```

Verify: Widget appears in upper-right, light green, pulsing, showing "Test task for widget" with "15 min" estimate and 2 navigation dots.

- [ ] **Step 3: Test play/pause/done flow**

1. Click Play → widget turns green (running), task timer starts in OmniFocus
2. Click Pause → widget turns gray, task paused
3. Click Play → resumes
4. Click Done → confetti, task slides out, next task fades in, undo button appears

- [ ] **Step 4: Test Caps Lock integration**

1. Select a task in OmniFocus, press Caps Lock → timer starts, LED on
2. Press Caps Lock again → task completes, LED off, confetti

- [ ] **Step 5: Test queue navigation**

1. Push multiple tasks to queue.json
2. Use ◀/▶ arrows to browse
3. Start a task, then click an arrow → current task pauses, browsed task shown

- [ ] **Step 6: Test undo**

1. Complete a task
2. Click the small undo button before it fades
3. Verify task is marked incomplete in OmniFocus and shows as paused

- [ ] **Step 7: Commit any fixes**

```bash
git add -A omnifocus-timer/TimerWidget/
git commit -m "fix(timer-widget): fixes from manual testing"
```

---

### Task 11: Launchd Plist for Auto-Start

**Files:**
- Create: `omnifocus-timer/com.dorsey.timer-widget.plist`

- [ ] **Step 1: Create launchd plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.dorsey.timer-widget</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/chaddorsey/Dropbox/dev/omnifocus-timer/TimerWidget/.build/release/TimerWidget</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

- [ ] **Step 2: Build release and install**

```bash
cd omnifocus-timer/TimerWidget
swift build -c release
cp com.dorsey.timer-widget.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.dorsey.timer-widget.plist
```

- [ ] **Step 3: Commit**

```bash
git add omnifocus-timer/com.dorsey.timer-widget.plist
git commit -m "feat(timer-widget): add launchd plist for auto-start on login"
```
