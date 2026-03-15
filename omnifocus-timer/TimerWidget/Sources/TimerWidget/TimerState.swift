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
        // Watch queue changes
        queueCancellable = queue.$tasks.sink { [weak self] tasks in
            guard let self = self else { return }
            self.onQueueChanged(tasks)
        }

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

        switch newState {
        case "running":
            widgetState = .running
            if let id = status?.taskId { currentTaskId = id; cachedTaskId = id }
            if let name = status?.taskName { currentTaskName = name; cachedTaskName = name }
            showUndo = false

        case "paused":
            widgetState = .paused
            if let id = status?.taskId { currentTaskId = id; cachedTaskId = id }
            if let name = status?.taskName { currentTaskName = name; cachedTaskName = name }
            showUndo = false

        case "idle":
            let wasActive = (previousPollState == "running" || previousPollState == "paused")
            if wasActive {
                // Timer just stopped — transition
                if !queue.tasks.isEmpty {
                    transitionToQueued(index: 0)
                } else {
                    widgetState = .lastCompleted
                    currentTaskId = cachedTaskId
                    currentTaskName = cachedTaskName
                    showUndo = true
                    undoTaskId = cachedTaskId
                    undoTaskName = cachedTaskName
                }
            } else {
                // Already idle
                if widgetState == .lastCompleted || widgetState == .completing {
                    // Stay in current state
                } else if !queue.tasks.isEmpty {
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
        guard !queue.tasks.isEmpty else { return }
        let clamped = min(index, queue.tasks.count - 1)
        queueIndex = clamped
        let task = queue.tasks[clamped]
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
            if !queue.tasks.isEmpty {
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
                if !self.queue.tasks.isEmpty {
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
            guard newIndex >= 0, newIndex < queue.tasks.count else { return }
            queueIndex = newIndex
            applyQueueItem(queue.tasks[newIndex])
        } else {
            // Browsing queue in queued state
            let newIndex = queueIndex + direction
            guard newIndex >= 0, newIndex < queue.tasks.count else { return }
            transitionToQueued(index: newIndex)
        }
    }

    func taskNameClicked() {
        guard !currentTaskId.isEmpty else { return }
        bridge.navigateToTask(taskId: currentTaskId)
    }
}
