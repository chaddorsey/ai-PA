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
    private var dirDescriptor: Int32 = -1
    private var dispatchSource: DispatchSourceFileSystemObject?
    private var pollTimer: Timer?
    private var lastModDate: Date?

    init() {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let dir = home.appendingPathComponent(".omnifocus-timer-widget")
        queueURL = dir.appendingPathComponent("queue.json")

        ensureFileExists(directory: dir)
        loadQueue()
        startWatching()
        startPolling()
    }

    deinit {
        dispatchSource?.cancel()
        pollTimer?.invalidate()
        if dirDescriptor >= 0 {
            close(dirDescriptor)
        }
    }

    func loadQueue() {
        guard FileManager.default.fileExists(atPath: queueURL.path) else {
            DispatchQueue.main.async { self.taskIds = [] }
            return
        }
        do {
            let attrs = try FileManager.default.attributesOfItem(atPath: queueURL.path)
            lastModDate = attrs[.modificationDate] as? Date

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

    /// Synchronous load — updates taskIds immediately on the calling thread.
    /// Use from the SIGHUP handler where resolve must see the new IDs.
    func loadQueueSync() {
        guard FileManager.default.fileExists(atPath: queueURL.path) else {
            taskIds = []
            return
        }
        do {
            let attrs = try FileManager.default.attributesOfItem(atPath: queueURL.path)
            lastModDate = attrs[.modificationDate] as? Date

            let data = try Data(contentsOf: queueURL)
            let file = try JSONDecoder().decode(QueueFile.self, from: data)
            taskIds = file.tasks
        } catch {
            taskIds = []
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

    // MARK: - Persistence

    func saveQueue() {
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
        stopWatching()
        // Watch the directory, not the file. This catches all write patterns:
        // atomic rename, in-place write, SSH writes, Python json.dump, etc.
        let dirPath = queueURL.deletingLastPathComponent().path
        dirDescriptor = open(dirPath, O_EVTONLY)
        guard dirDescriptor >= 0 else { return }

        let source = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: dirDescriptor,
            eventMask: [.write, .rename, .attrib],
            queue: .main
        )

        source.setEventHandler { [weak self] in
            self?.loadQueue()
        }

        source.setCancelHandler { [weak self] in
            if let fd = self?.dirDescriptor, fd >= 0 {
                close(fd)
                self?.dirDescriptor = -1
            }
        }

        source.resume()
        dispatchSource = source
    }

    private func stopWatching() {
        dispatchSource?.cancel()
        dispatchSource = nil
    }

    /// Poll every 5 seconds as a fallback for stale file watchers
    private func startPolling() {
        pollTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
            self?.checkForChanges()
        }
    }

    private func checkForChanges() {
        guard FileManager.default.fileExists(atPath: queueURL.path) else { return }
        do {
            let attrs = try FileManager.default.attributesOfItem(atPath: queueURL.path)
            let modDate = attrs[.modificationDate] as? Date
            if let modDate, modDate != lastModDate {
                lastModDate = modDate
                loadQueue()
            }
        } catch {}
    }
}
