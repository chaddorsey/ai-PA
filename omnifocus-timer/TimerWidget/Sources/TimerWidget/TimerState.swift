import Foundation
import Combine

enum WidgetState: Equatable {
    case idle
    case queued
    case running
    case paused
    case completing
    case lastCompleted
}

final class TimerState: ObservableObject {
    // MARK: - Published State

    @Published var widgetState: WidgetState = .idle {
        didSet {
            if widgetState != oldValue {
                let trace = Thread.callStackSymbols.prefix(5).joined(separator: "\n  ")
                print("[state] \(oldValue) → \(widgetState)\n  \(trace)")
            }
        }
    }
    @Published var currentTaskId: String = ""
    @Published var currentTaskName: String = ""
    @Published var currentEstimateMin: Int? = nil
    @Published var queueIndex: Int = 0
    @Published var showUndo: Bool = false
    @Published var undoTaskId: String = ""
    @Published var undoTaskName: String = ""

    // MARK: - Internal

    let bridge = OmniFocusBridge()
    let queue = QueueManager()

    /// Queue tasks excluding the currently active task
    var visibleQueue: [QueuedTask] {
        let activeId = currentTaskId
        if activeId.isEmpty {
            return queue.resolvedTasks
        }
        return queue.resolvedTasks.filter { $0.taskId != activeId }
    }

    private var previousPollState: String = "idle"
    private var cachedTaskId: String = ""
    private var cachedTaskName: String = ""
    private var pollCancellable: AnyCancellable?
    private var queueCancellable: AnyCancellable?
    private var userActionGraceUntil: Date = .distantPast

    init() {
        // Watch queue ID changes (file watcher triggers this)
        queueCancellable = queue.$taskIds.sink { [weak self] _ in
            guard let self = self else { return }
            // Re-resolve on next poll
        }

        // Watch resolved tasks for UI updates — only fire when IDs actually change
        queue.$taskIds
            .removeDuplicates()
            .sink { [weak self] _ in
                guard let self = self else { return }
                self.onQueueChanged(self.queue.resolvedTasks)
            }
            .store(in: &cancellables)

        startPolling()
    }

    private var cancellables = Set<AnyCancellable>()

    // MARK: - Polling

    private func startPolling() {
        poll()
    }

    private func poll() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            let status = self.bridge.getTimerStatus()
            // Resolve queue task details from OmniFocus
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
    /// This prevents the poll from overriding optimistic UI updates before the
    /// osascript command has propagated to OmniFocus.
    private func beginUserActionGrace() {
        userActionGraceUntil = Date().addingTimeInterval(4.0)
    }

    private var isInGracePeriod: Bool {
        Date() < userActionGraceUntil
    }

    private func handlePollResult(_ status: TimerStatusResponse?) {
        let newState = status?.state ?? "idle"
        if status == nil {
            print("[poll] OmniFocus unavailable")
        } else {
            print("[poll] state=\(newState) task=\(status?.taskName ?? "nil")")
        }

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
            widgetState = .running
            if let id = status?.taskId { currentTaskId = id; cachedTaskId = id }
            if let name = status?.taskName { currentTaskName = name; cachedTaskName = name }
            if let est = status?.originalEstimate { currentEstimateMin = est }
            showUndo = false
            autoQueueRunningTask()

        case "paused":
            widgetState = .paused
            if let id = status?.taskId { currentTaskId = id; cachedTaskId = id }
            if let name = status?.taskName { currentTaskName = name; cachedTaskName = name }
            if let est = status?.originalEstimate { currentEstimateMin = est }
            showUndo = false

        case "idle":
            let wasActive = (previousPollState == "running" || previousPollState == "paused")
            if wasActive && widgetState != .completing && widgetState != .lastCompleted {
                // Timer just stopped externally (Caps Lock, CLI, etc.) — trigger completion
                currentTaskId = cachedTaskId
                currentTaskName = cachedTaskName
                undoTaskId = cachedTaskId
                undoTaskName = cachedTaskName
                widgetState = .completing
                showUndo = true

                // After a brief delay for confetti, transition to next state
                DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) { [weak self] in
                    guard let self = self, self.widgetState == .completing else { return }
                    if !self.visibleQueue.isEmpty {
                        self.transitionToQueued(index: 0)
                    } else {
                        self.widgetState = .lastCompleted
                    }
                }
            } else {
                // Already idle
                if widgetState == .lastCompleted || widgetState == .completing {
                    // Stay in current state
                } else if !visibleQueue.isEmpty {
                    transitionToQueued(index: 0)
                } else {
                    widgetState = .idle
                }
            }

        default:
            break
        }

        previousPollState = newState
    }

    // MARK: - Queue Management

    private func onQueueChanged(_ tasks: [QueuedTask]) {
        print("[queue] changed: \(tasks.count) IDs, state=\(widgetState)")
        // Only transition to idle from queued state when queue is truly empty
        // and no grace period is active
        if widgetState == .idle && !tasks.isEmpty {
            transitionToQueued(index: 0)
        } else if widgetState == .queued && tasks.isEmpty && !isInGracePeriod {
            widgetState = .idle
            currentTaskId = ""
            currentTaskName = ""
            currentEstimateMin = nil
        } else if widgetState == .queued && !tasks.isEmpty && queueIndex >= tasks.count {
            queueIndex = max(0, tasks.count - 1)
            if !tasks.isEmpty {
                applyQueueItem(tasks[queueIndex])
            }
        }
    }

    private func transitionToQueued(index: Int) {
        let vq = visibleQueue
        guard !vq.isEmpty else { return }
        let clamped = min(index, vq.count - 1)
        queueIndex = clamped
        let task = vq[clamped]
        applyQueueItem(task)
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
            widgetState = .running  // Set BEFORE queue removal to prevent idle flash
            queue.removeTask(id: taskId)
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                self?.bridge.startTimer(taskId: taskId)
            }

        case .paused:
            widgetState = .running
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                self?.bridge.resumeTimer()
            }

        case .lastCompleted:
            if !visibleQueue.isEmpty {
                transitionToQueued(index: 0)
            }

        default:
            break
        }
    }

    func pausePressed() {
        guard widgetState == .running else { return }
        beginUserActionGrace()
        widgetState = .paused
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

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.bridge.completeTask(taskId: taskId)
            DispatchQueue.main.async {
                guard let self = self else { return }
                if !self.visibleQueue.isEmpty {
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
            bridge.pauseTimer()
            widgetState = .paused
        }

        let vq = visibleQueue
        if widgetState == .paused {
            // Show queue items while paused
            let newIndex = queueIndex + direction
            guard newIndex >= 0, newIndex < vq.count else { return }
            queueIndex = newIndex
            applyQueueItem(vq[newIndex])
        } else {
            // Browsing queue in queued state
            let newIndex = queueIndex + direction
            guard newIndex >= 0, newIndex < vq.count else { return }
            transitionToQueued(index: newIndex)
        }
    }

    func taskNameClicked() {
        guard !currentTaskId.isEmpty else { return }
        bridge.navigateToTask(taskId: currentTaskId)
    }

    // Dequeue animation state
    @Published var isDequeuing: Bool = false
    @Published var dequeueTaskName: String = ""

    /// Remove current task from queue without completing it (paused/queued only)
    func dequeueCurrentTask() {
        guard widgetState == .paused || widgetState == .queued else { return }
        guard !currentTaskId.isEmpty else { return }

        // If paused, stop the timer but don't complete
        if widgetState == .paused {
            bridge.pauseTimer() // ensure paused state
        }

        let removedId = currentTaskId
        dequeueTaskName = currentTaskName
        isDequeuing = true

        // Remove from queue
        queue.removeTask(id: removedId)

        // After animation (2s), transition to next task or idle
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            guard let self = self else { return }
            self.isDequeuing = false
            self.dequeueTaskName = ""

            let vq = self.visibleQueue
            if !vq.isEmpty {
                self.transitionToQueued(index: 0)
            } else {
                self.widgetState = .idle
            }
        }
    }

    /// Add selected OmniFocus tasks to the queue (called by plus button)
    func queueSelectedTasks() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            let ids = self.bridge.getSelectedTaskIds()
            guard !ids.isEmpty else { return }
            DispatchQueue.main.async {
                for id in ids {
                    if !self.queue.taskIds.contains(id) {
                        self.queue.taskIds.append(id)
                    }
                }
                self.queue.saveQueue()
                // Trigger resolve on next poll, but also do it now
                DispatchQueue.global(qos: .userInitiated).async {
                    self.queue.resolveFromOmniFocus(bridge: self.bridge)
                }
            }
        }
    }

    /// Auto-queue a running task that isn't in the queue
    func autoQueueRunningTask() {
        guard !currentTaskId.isEmpty else { return }
        if !queue.taskIds.contains(currentTaskId) {
            queue.taskIds.insert(currentTaskId, at: 0)
            queue.saveQueue()
        }
    }
}
