import Foundation
import AppKit

struct TimerStatusResponse {
    let state: String   // "running", "paused", "idle"
    let taskId: String?
    let taskName: String?
    let elapsedSeconds: Int?
}

final class OmniFocusBridge {

    // MARK: - Polling

    func getTimerStatus() -> TimerStatusResponse? {
        let js = """
        (function() {
            var lib = PlugIn.find('com.dorsey.omnifocus-timer').library('timerLib');
            var s = lib.getTimerStatus();
            return JSON.stringify(s);
        })()
        """
        guard let raw = evaluateJS(js) else { return nil }
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        let state = obj["status"] as? String ?? "idle"
        return TimerStatusResponse(
            state: state,
            taskId: obj["taskId"] as? String,
            taskName: obj["taskName"] as? String,
            elapsedSeconds: obj["elapsedSeconds"] as? Int
        )
    }

    // MARK: - Commands

    func startTimer(taskId: String) {
        let js = """
        (function() {
            var lib = PlugIn.find('com.dorsey.omnifocus-timer').library('timerLib');
            lib.startTimerOnTask('\(escapeJS(taskId))');
            return 'ok';
        })()
        """
        _ = evaluateJS(js)
    }

    func pauseTimer() {
        let js = """
        (function() {
            var lib = PlugIn.find('com.dorsey.omnifocus-timer').library('timerLib');
            lib.pauseTimer();
            return 'ok';
        })()
        """
        _ = evaluateJS(js)
    }

    func resumeTimer() {
        let js = """
        (function() {
            var lib = PlugIn.find('com.dorsey.omnifocus-timer').library('timerLib');
            lib.resumeTimer();
            return 'ok';
        })()
        """
        _ = evaluateJS(js)
    }

    func completeTask(taskId: String) {
        let js = """
        (function() {
            var lib = PlugIn.find('com.dorsey.omnifocus-timer').library('timerLib');
            lib.stopTimer();
            var task = Task.byIdentifier('\(escapeJS(taskId))');
            if (task) { task.markComplete(); }
            return 'ok';
        })()
        """
        _ = evaluateJS(js)
    }

    func undoComplete(taskId: String) {
        let js = """
        (function() {
            var task = Task.byIdentifier('\(escapeJS(taskId))');
            if (task) { task.markIncomplete(); }
            return 'ok';
        })()
        """
        _ = evaluateJS(js)
    }

    func navigateToTask(taskId: String) {
        let urlString = "omnifocus:///task/\(taskId)"
        if let url = URL(string: urlString) {
            NSWorkspace.shared.open(url)
        }
    }

    // MARK: - Private

    private func escapeJS(_ s: String) -> String {
        return s
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "'", with: "\\'")
            .replacingOccurrences(of: "\n", with: "\\n")
    }

    private func evaluateJS(_ js: String) -> String? {
        let escaped = js
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\n", with: "\\n")

        let appleScript = """
        tell application "OmniFocus" to evaluate javascript "\(escaped)"
        """

        let tempFile = FileManager.default.temporaryDirectory
            .appendingPathComponent("of_bridge_\(ProcessInfo.processInfo.processIdentifier).scpt")
        do {
            try appleScript.write(to: tempFile, atomically: true, encoding: .utf8)
        } catch {
            print("[bridge] Failed to write temp file: \(error)")
            return nil
        }
        defer { try? FileManager.default.removeItem(at: tempFile) }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = [tempFile.path]

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            print("[bridge] Failed to run osascript: \(error)")
            return nil
        }

        let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
        if let stderrStr = String(data: stderrData, encoding: .utf8), !stderrStr.isEmpty {
            print("[bridge] osascript stderr: \(stderrStr.trimmingCharacters(in: .whitespacesAndNewlines))")
        }

        guard process.terminationStatus == 0 else {
            print("[bridge] osascript exit code: \(process.terminationStatus)")
            return nil
        }

        let data = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
        var result = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)

        // osascript may double-quote the output
        if let r = result, r.hasPrefix("\"") && r.hasSuffix("\"") && r.count >= 2 {
            result = String(r.dropFirst().dropLast())
            // Unescape backslash-escaped quotes inside
            result = result?.replacingOccurrences(of: "\\\"", with: "\"")
        }

        return result
    }
}
