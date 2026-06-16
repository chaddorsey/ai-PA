import Cocoa

class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSAppleEventManager.shared().setEventHandler(
            self,
            andSelector: #selector(handleURL(event:reply:)),
            forEventClass: AEEventClass(kInternetEventClass),
            andEventID: AEEventID(kAEGetURL)
        )
    }

    @objc func handleURL(event: NSAppleEventDescriptor, reply: NSAppleEventDescriptor) {
        guard let urlString = event.paramDescriptor(forKeyword: AEKeyword(keyDirectObject))?.stringValue else { return }

        // Strip scheme prefix to get raw path, handling percent-encoding
        let prefix = "openfile://"
        guard urlString.hasPrefix(prefix) else { return }
        let rawPath = String(urlString.dropFirst(prefix.count))
        guard let path = rawPath.removingPercentEncoding, !path.isEmpty else { return }

        // Expand a leading ~ (or ~user) so machine-agnostic openfile://~/… links
        // resolve to the LOCAL user's home — the handler runs on the machine where the
        // click happens (laptop on laptop, server on server). Absolute paths (leading /)
        // pass through expandingTildeInPath unchanged, so old links keep working.
        let expanded = (path as NSString).expandingTildeInPath
        NSWorkspace.shared.open(URL(fileURLWithPath: expanded))
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
