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

        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
