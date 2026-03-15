import Foundation
import Combine

struct QueuedTask: Identifiable {
    let taskId: String
    var taskName: String
    var estimateMin: Int?

    var id: String { taskId }
}

struct QueueFile: Codable {
    var tasks: [String]  // just task IDs
}

final class QueueManager: ObservableObject {
    @Published var taskIds: [String] = []
    @Published var resolvedTasks: [QueuedTask] = []

    private let queueURL: URL
    private var fileDescriptor: Int32 = -1
    private var dispatchSource: DispatchSourceFileSystemObject?

    init() {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let dir = home.appendingPathComponent(".omnifocus-timer-widget")
        queueURL = dir.appendingPathComponent("queue.json")

        ensureFileExists(directory: dir)
        loadQueue()
        startWatching()
    }

    deinit {
        dispatchSource?.cancel()
        if fileDescriptor >= 0 {
            close(fileDescriptor)
        }
    }

    func loadQueue() {
        guard FileManager.default.fileExists(atPath: queueURL.path) else {
            DispatchQueue.main.async { self.taskIds = [] }
            return
        }
        do {
            let data = try Data(contentsOf: queueURL)
            let file = try JSONDecoder().decode(QueueFile.self, from: data)
            DispatchQueue.main.async {
                self.taskIds = file.tasks
            }
        } catch {
            DispatchQueue.main.async {
                self.taskIds = []
            }
        }
    }

    /// Resolve task details from OmniFocus for all queued IDs.
    /// Called from the poll loop with the bridge.
    func resolveFromOmniFocus(bridge: OmniFocusBridge) {
        var resolved: [QueuedTask] = []
        for taskId in taskIds {
            if let info = bridge.getTaskInfo(taskId: taskId) {
                resolved.append(QueuedTask(
                    taskId: taskId,
                    taskName: info.name,
                    estimateMin: info.estimateMin
                ))
            } else {
                // Task not found in OmniFocus — keep ID, mark as unknown
                resolved.append(QueuedTask(
                    taskId: taskId,
                    taskName: "Unknown task",
                    estimateMin: nil
                ))
            }
        }
        DispatchQueue.main.async {
            self.resolvedTasks = resolved
        }
    }

    func removeTask(id: String) {
        taskIds.removeAll { $0 == id }
        resolvedTasks.removeAll { $0.taskId == id }
        saveQueue()
    }

    // MARK: - Private

    private func saveQueue() {
        let file = QueueFile(tasks: taskIds)
        do {
            let data = try JSONEncoder().encode(file)
            try data.write(to: queueURL, options: .atomic)
        } catch {
            // Silently fail — queue persistence is best-effort
        }
    }

    private func ensureFileExists(directory: URL) {
        let fm = FileManager.default
        if !fm.fileExists(atPath: directory.path) {
            try? fm.createDirectory(at: directory, withIntermediateDirectories: true)
        }
        if !fm.fileExists(atPath: queueURL.path) {
            let empty = QueueFile(tasks: [])
            if let data = try? JSONEncoder().encode(empty) {
                try? data.write(to: queueURL, options: .atomic)
            }
        }
    }

    private func startWatching() {
        fileDescriptor = open(queueURL.path, O_EVTONLY)
        guard fileDescriptor >= 0 else { return }

        let source = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: fileDescriptor,
            eventMask: [.write, .rename, .delete],
            queue: .main
        )

        source.setEventHandler { [weak self] in
            self?.loadQueue()
        }

        source.setCancelHandler { [weak self] in
            if let fd = self?.fileDescriptor, fd >= 0 {
                close(fd)
                self?.fileDescriptor = -1
            }
        }

        source.resume()
        dispatchSource = source
    }
}
