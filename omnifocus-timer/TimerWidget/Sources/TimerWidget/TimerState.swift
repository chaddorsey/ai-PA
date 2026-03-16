import Foundation
import Combine

enum WidgetState: Equatable {
    case idle
    case queued
    case running
    case paused
    case collapsed      // Paused/queued task minimized to small rectangle
    case completing
    case lastCompleted
}

final class TimerState: ObservableObject {
    // MARK: - Published State

    @Published var widgetState: WidgetState = .idle
    @Published var currentTaskId: String = ""
    @Published var currentTaskName: String = ""
    @Published var currentEstimateMin: Int? = nil
    @Published var queueIndex: Int = 0
    @Published var showUndo: Bool = false
    @Published var undoTaskId: String = ""
    @Published var undoTaskName: String = ""

    // Dequeue animation state
    @Published var isDequeuing: Bool = false
    @Published var dequeueTaskName: String = ""

    // Queue count for SwiftUI view reactivity
    @Published var queueCount: Int = 0

    // MARK: - Internal

    let bridge = OmniFocusBridge()
    let queue = QueueManager()

    private var previousPollState: String = "idle"
    private var cachedTaskId: String = ""
    private var cachedTaskName: String = ""
    private var pollCancellable: AnyCancellable?
    private var userActionGraceUntil: Date = .distantPast
    private var suppressCompletionUntil: Date = .distantPast
    var dismissedByInactivity: Bool = false
    private var collapseTimer: AnyCancellable?

    /// How long to wait before collapsing a paused widget. Default 2 min. Set low for testing.
    var collapseDelay: TimeInterval = 120
    private var cancellables = Set<AnyCancellable>()

    init() {
        // Watch queue ID changes — only handle idle->queued transition
        queue.$taskIds
            .removeDuplicates()
            .sink { [weak self] ids in
                guard let self = self else { return }
                self.onQueueChanged(ids)
            }
            .store(in: &cancellables)

        startPolling()
    }

    // MARK: - Polling

    private func startPolling() {
        poll()
    }

    private func poll() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            let status = self.bridge.getTimerStatus()
            self.queue.resolveFromOmniFocus(bridge: self.bridge)

            DispatchQueue.main.async {
                self.handlePollResult(status)
                self.scheduleNextPoll()
            }
        }
    }

    private func scheduleNextPoll() {
        pollCancellable = Just(())
            .delay(for: .seconds(2), scheduler: DispatchQueue.main)
            .sink { [weak self] _ in
                self?.poll()
            }
    }

    /// Suppress poll-driven state changes for a grace period after user actions.
    private func beginUserActionGrace() {
        userActionGraceUntil = Date().addingTimeInterval(4.0)
        dismissedByInactivity = false
    }

    private var isInGracePeriod: Bool {
        Date() < userActionGraceUntil
    }

    private func handlePollResult(_ status: TimerStatusResponse?) {
        let newState = status?.state ?? "idle"
        print("[poll] state=\(newState) widget=\(widgetState) queue=\(queue.taskIds.count) grace=\(isInGracePeriod)")

        // During grace period, only update task info but don't change widget state
        if isInGracePeriod {
            if let id = status?.taskId { cachedTaskId = id }
            if let name = status?.taskName { cachedTaskName = name }
            if let est = status?.originalEstimate { currentEstimateMin = est }
            previousPollState = newState
            return
        }

        switch newState {
        case "running":
            dismissedByInactivity = false
            cancelCollapseTimer()
            widgetState = .running
            if let id = status?.taskId { currentTaskId = id; cachedTaskId = id }
            if let name = status?.taskName { currentTaskName = name; cachedTaskName = name }
            if let est = status?.originalEstimate { currentEstimateMin = est }
            showUndo = false
            autoQueueRunningTask()

        case "paused":
            if widgetState != .paused && widgetState != .collapsed {
                widgetState = .paused
                startCollapseTimer()
            }
            if let id = status?.taskId { currentTaskId = id; cachedTaskId = id }
            if let name = status?.taskName { currentTaskName = name; cachedTaskName = name }
            if let est = status?.originalEstimate { currentEstimateMin = est }
            showUndo = false

        case "idle":
            let wasActive = (previousPollState == "running" || previousPollState == "paused")
            let suppressCompletion = Date() < suppressCompletionUntil

            if wasActive && !suppressCompletion && widgetState != .completing && widgetState != .lastCompleted {
                // Timer stopped externally (Caps Lock, CLI, etc.) — trigger completion
                currentTaskId = cachedTaskId
                currentTaskName = cachedTaskName
                undoTaskId = cachedTaskId
                undoTaskName = cachedTaskName
                widgetState = .completing
                showUndo = true

                // Remove completed task from queue
                if !cachedTaskId.isEmpty {
                    queue.removeTask(id: cachedTaskId)
                }

                // After confetti, transition to next state
                DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) { [weak self] in
                    guard let self = self, self.widgetState == .completing else { return }
                    if !self.queue.taskIds.isEmpty {
                        self.transitionToQueued(index: 0)
                    } else {
                        self.widgetState = .lastCompleted
                    }
                }
            } else {
                // Already idle or suppressed
                if widgetState == .lastCompleted || widgetState == .completing || widgetState == .queued {
                    // Stay in current state — don't reset queue index or re-trigger transitions
                } else if widgetState == .idle && !queue.taskIds.isEmpty && !dismissedByInactivity {
                    transitionToQueued(index: 0)
                }
            }

        default:
            break
        }

        previousPollState = newState
    }

    // MARK: - Queue Management

    /// Called when queue taskIds change. ONLY handles idle->queued.
    /// Never sets idle — that is the poll's responsibility.
    private func onQueueChanged(_ ids: [String]) {
        print("[queue] ids changed: \(ids.count) ids, widget=\(widgetState)")
        queueCount = ids.count
        if widgetState == .idle && !ids.isEmpty && !dismissedByInactivity {
            transitionToQueued(index: 0)
        } else if (widgetState == .queued || widgetState == .paused) && !ids.isEmpty && queueIndex >= ids.count {
            // Queue shrunk while viewing — clamp index
            queueIndex = max(0, ids.count - 1)
            let resolved = queue.resolvedTasks
            if queueIndex < resolved.count {
                applyQueueItem(resolved[queueIndex])
            }
        }
    }

    private func transitionToQueued(index: Int) {
        let resolved = queue.resolvedTasks
        guard !resolved.isEmpty else { return }
        let clamped = min(index, resolved.count - 1)
        queueIndex = clamped
        applyQueueItem(resolved[clamped])
        widgetState = .queued
    }

    private func applyQueueItem(_ task: QueuedTask) {
        currentTaskId = task.taskId
        currentTaskName = task.taskName
        currentEstimateMin = task.estimateMin
    }

    // MARK: - User Actions

    func playPressed() {
        beginUserActionGrace()
        switch widgetState {
        case .queued:
            let taskId = currentTaskId
            cachedTaskId = currentTaskId
            cachedTaskName = currentTaskName
            widgetState = .running
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                self?.bridge.startTimer(taskId: taskId)
            }

        case .paused:
            widgetState = .running
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                self?.bridge.resumeTimer()
            }

        case .lastCompleted:
            if !queue.taskIds.isEmpty {
                transitionToQueued(index: 0)
            }

        default:
            break
        }
    }

    func pausePressed() {
        guard widgetState == .running else { return }
        beginUserActionGrace()
        cancelCollapseTimer()
        widgetState = .paused
        startCollapseTimer()
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.bridge.pauseTimer()
        }
    }

    func donePressed() {
        guard widgetState == .running || widgetState == .paused else { return }
        beginUserActionGrace()
        widgetState = .completing
        let taskId = currentTaskId
        undoTaskId = taskId
        undoTaskName = currentTaskName

        // Remove completed task from queue
        queue.removeTask(id: taskId)

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.bridge.completeTask(taskId: taskId)
            DispatchQueue.main.async {
                guard let self = self else { return }
                if !self.queue.taskIds.isEmpty {
                    self.transitionToQueued(index: 0)
                } else {
                    self.widgetState = .lastCompleted
                    self.showUndo = true
                }
            }
        }
    }

    func undoPressed() {
        guard showUndo, !undoTaskId.isEmpty else { return }
        bridge.undoComplete(taskId: undoTaskId)
        showUndo = false
        widgetState = .idle
    }

    func navigateQueue(direction: Int) {
        guard widgetState == .queued || widgetState == .paused || widgetState == .running else { return }

        // Auto-pause if running
        if widgetState == .running {
            beginUserActionGrace()
            widgetState = .paused
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                self?.bridge.pauseTimer()
            }
        }

        let ids = queue.taskIds
        let newIndex = queueIndex + direction
        guard newIndex >= 0, newIndex < ids.count else { return }

        let resolved = queue.resolvedTasks
        guard newIndex < resolved.count else { return }

        queueIndex = newIndex
        applyQueueItem(resolved[newIndex])

        if widgetState == .queued {
            // Already queued, just update index/task
        }
        // If paused, stay paused with new task displayed
    }

    func taskNameClicked() {
        guard !currentTaskId.isEmpty else { return }
        bridge.navigateToTask(taskId: currentTaskId)
    }

    /// Remove current task from queue without completing it (paused/queued only)
    func dequeueCurrentTask() {
        guard widgetState == .paused || widgetState == .queued else { return }
        guard !currentTaskId.isEmpty else { return }
        beginUserActionGrace()
        // Suppress completion detection — this is a dequeue, not a completion
        suppressCompletionUntil = Date().addingTimeInterval(6.0)

        // Stop the timer if paused so it doesn't reappear from poll
        if widgetState == .paused {
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                self?.bridge.stopTimer()
            }
        }

        let removedId = currentTaskId
        dequeueTaskName = currentTaskName

        // Signal the animation BEFORE removing (so AppDelegate can snapshot)
        isDequeuing = true

        // Remove from queue
        queue.removeTask(id: removedId)

        // Transition to next task immediately (ghost animation plays independently)
        if !queue.taskIds.isEmpty {
            transitionToQueued(index: 0)
        } else {
            widgetState = .idle
            currentTaskId = ""
            currentTaskName = ""
            currentEstimateMin = nil
        }

        // Clean up dequeue state after animation completes
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) { [weak self] in
            self?.isDequeuing = false
            self?.dequeueTaskName = ""
        }
    }

    /// Add selected OmniFocus tasks to the queue
    func queueSelectedTasks() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            let ids = self.bridge.getSelectedTaskIds()
            guard !ids.isEmpty else { return }
            DispatchQueue.main.async {
                self.dismissedByInactivity = false
                for id in ids {
                    if !self.queue.taskIds.contains(id) {
                        self.queue.taskIds.append(id)
                    }
                }
                self.queue.saveQueue()
                self.queueCount = self.queue.taskIds.count
                // Resolve task details now
                DispatchQueue.global(qos: .userInitiated).async {
                    self.queue.resolveFromOmniFocus(bridge: self.bridge)
                }
            }
        }
    }

    // MARK: - Collapse / Expand

    func startCollapseTimer() {
        collapseTimer?.cancel()
        collapseTimer = Just(())
            .delay(for: .seconds(collapseDelay), scheduler: DispatchQueue.main)
            .sink { [weak self] in
                guard let self = self else { return }
                if self.widgetState == .paused || self.widgetState == .queued {
                    self.widgetState = .collapsed
                }
            }
    }

    func cancelCollapseTimer() {
        collapseTimer?.cancel()
        collapseTimer = nil
    }

    /// Expand from collapsed state back to queued/paused
    func expandFromCollapsed() {
        guard widgetState == .collapsed else { return }
        // If there's a cached task that was paused, go to paused
        // Otherwise go to queued
        if !currentTaskId.isEmpty && previousPollState == "paused" {
            widgetState = .paused
        } else {
            widgetState = .queued
        }
        // Restart collapse timer
        startCollapseTimer()
    }

    /// Force collapse for testing
    func forceCollapse() {
        if widgetState == .paused || widgetState == .queued {
            widgetState = .collapsed
        }
    }

    /// Auto-queue a running task that isn't in the queue.
    /// Inserts at position 0 and sets queueIndex to point at it.
    private func autoQueueRunningTask() {
        guard !currentTaskId.isEmpty else { return }
        if !queue.taskIds.contains(currentTaskId) {
            queue.taskIds.insert(currentTaskId, at: 0)
            queueIndex = 0
            queue.saveQueue()
            queueCount = queue.taskIds.count
        }
    }
}
