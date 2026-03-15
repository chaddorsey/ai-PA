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

    @Published var widgetState: WidgetState = .idle
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

    private var previousPollState: String = "idle"
    private var cachedTaskId: String = ""
    private var cachedTaskName: String = ""
    private var pollCancellable: AnyCancellable?
    private var queueCancellable: AnyCancellable?

    init() {
        // Watch queue ID changes (file watcher triggers this)
        queueCancellable = queue.$taskIds.sink { [weak self] _ in
            guard let self = self else { return }
            // Re-resolve on next poll
        }

        // Watch resolved tasks for UI updates
        queue.$resolvedTasks.sink { [weak self] tasks in
            guard let self = self else { return }
            self.onQueueChanged(tasks)
        }.store(in: &cancellables)

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

    private func handlePollResult(_ status: TimerStatusResponse?) {
        let newState = status?.state ?? "idle"
        if status == nil {
            print("[poll] OmniFocus unavailable")
        } else {
            print("[poll] state=\(newState) task=\(status?.taskName ?? "nil")")
        }

        switch newState {
        case "running":
            widgetState = .running
            if let id = status?.taskId { currentTaskId = id; cachedTaskId = id }
            if let name = status?.taskName { currentTaskName = name; cachedTaskName = name }
            if let est = status?.originalEstimate { currentEstimateMin = est }
            showUndo = false

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
                    if !self.queue.resolvedTasks.isEmpty {
                        self.transitionToQueued(index: 0)
                    } else {
                        self.widgetState = .lastCompleted
                    }
                }
            } else {
                // Already idle
                if widgetState == .lastCompleted || widgetState == .completing {
                    // Stay in current state
                } else if !queue.resolvedTasks.isEmpty {
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
        if widgetState == .idle && !tasks.isEmpty {
            transitionToQueued(index: 0)
        } else if widgetState == .queued && tasks.isEmpty {
            widgetState = .idle
            currentTaskId = ""
            currentTaskName = ""
            currentEstimateMin = nil
        } else if widgetState == .queued && queueIndex >= tasks.count {
            queueIndex = max(0, tasks.count - 1)
            if !tasks.isEmpty {
                applyQueueItem(tasks[queueIndex])
            }
        }
    }

    private func transitionToQueued(index: Int) {
        guard !queue.resolvedTasks.isEmpty else { return }
        let clamped = min(index, queue.resolvedTasks.count - 1)
        queueIndex = clamped
        let task = queue.resolvedTasks[clamped]
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
        switch widgetState {
        case .queued:
            bridge.startTimer(taskId: currentTaskId)
            queue.removeTask(id: currentTaskId)
            cachedTaskId = currentTaskId
            cachedTaskName = currentTaskName
            widgetState = .running

        case .paused:
            bridge.resumeTimer()
            widgetState = .running

        case .lastCompleted:
            if !queue.resolvedTasks.isEmpty {
                transitionToQueued(index: 0)
            }

        default:
            break
        }
    }

    func pausePressed() {
        guard widgetState == .running else { return }
        bridge.pauseTimer()
        widgetState = .paused
    }

    func donePressed() {
        guard widgetState == .running || widgetState == .paused else { return }
        widgetState = .completing
        let taskId = currentTaskId
        undoTaskId = taskId
        undoTaskName = currentTaskName

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.bridge.completeTask(taskId: taskId)
            DispatchQueue.main.async {
                guard let self = self else { return }
                if !self.queue.resolvedTasks.isEmpty {
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

        if widgetState == .paused {
            // Show queue items while paused
            let newIndex = queueIndex + direction
            guard newIndex >= 0, newIndex < queue.resolvedTasks.count else { return }
            queueIndex = newIndex
            applyQueueItem(queue.resolvedTasks[newIndex])
        } else {
            // Browsing queue in queued state
            let newIndex = queueIndex + direction
            guard newIndex >= 0, newIndex < queue.resolvedTasks.count else { return }
            transitionToQueued(index: newIndex)
        }
    }

    func taskNameClicked() {
        guard !currentTaskId.isEmpty else { return }
        bridge.navigateToTask(taskId: currentTaskId)
    }
}
