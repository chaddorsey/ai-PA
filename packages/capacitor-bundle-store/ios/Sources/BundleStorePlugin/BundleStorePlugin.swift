import Foundation
import Capacitor
import ZIPFoundation

@objc(BundleStorePlugin)
public class BundleStorePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "BundleStorePlugin"
    public let jsName = "BundleStore"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "download", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getPath", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "list", returnType: CAPPluginReturnPromise),
    ]

    private func bundlesDirectory() throws -> URL {
        let docs = try FileManager.default.url(
            for: .documentDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let bundlesDir = docs.appendingPathComponent("bundles", isDirectory: true)
        try FileManager.default.createDirectory(at: bundlesDir, withIntermediateDirectories: true)
        return bundlesDir
    }

    @objc func download(_ call: CAPPluginCall) {
        guard let legId = call.getString("legId"), !legId.isEmpty else {
            call.reject("Missing required parameter: legId")
            return
        }
        guard let urlString = call.getString("url"), let remoteURL = URL(string: urlString) else {
            call.reject("Missing or invalid parameter: url")
            return
        }

        // Sanitize legId to prevent path traversal
        let safeLegId = legId.replacingOccurrences(of: "/", with: "_")
                              .replacingOccurrences(of: "..", with: "_")

        let session = URLSession.shared
        let task = session.downloadTask(with: remoteURL) { [weak self] tempURL, response, error in
            guard let self = self else { return }

            if let error = error {
                call.reject("Download failed: \(error.localizedDescription)")
                return
            }
            guard let tempURL = tempURL else {
                call.reject("Download failed: no temporary file returned")
                return
            }

            do {
                let bundlesDir = try self.bundlesDirectory()
                let legDir = bundlesDir.appendingPathComponent(safeLegId, isDirectory: true)

                // Remove existing bundle if present
                if FileManager.default.fileExists(atPath: legDir.path) {
                    try FileManager.default.removeItem(at: legDir)
                }
                try FileManager.default.createDirectory(at: legDir, withIntermediateDirectories: true)

                // Unzip the downloaded file into the leg directory
                try FileManager.default.unzipItem(at: tempURL, to: legDir)

                call.resolve()
            } catch {
                call.reject("Failed to extract bundle: \(error.localizedDescription)")
            }
        }
        task.resume()
    }

    @objc func getPath(_ call: CAPPluginCall) {
        guard let legId = call.getString("legId"), !legId.isEmpty else {
            call.reject("Missing required parameter: legId")
            return
        }

        let safeLegId = legId.replacingOccurrences(of: "/", with: "_")
                              .replacingOccurrences(of: "..", with: "_")

        do {
            let bundlesDir = try bundlesDirectory()
            let legDir = bundlesDir.appendingPathComponent(safeLegId, isDirectory: true)
            let bundleJson = legDir.appendingPathComponent("bundle.json")

            guard FileManager.default.fileExists(atPath: bundleJson.path) else {
                call.reject("Bundle not found for legId: \(legId). Download it first.")
                return
            }

            // Convert the native file URL to a WebView-loadable URL using Capacitor's
            // local file-serving scheme. Capacitor serves Documents/ via the scheme:
            //   capacitor://localhost/_capacitor_file_/path/to/file
            //
            // NOTE: This URL form must be verified on a real device / simulator.
            // The exact scheme and prefix used by Capacitor's WKURLSchemeHandler varies
            // by Capacitor version. If `bridge?.portablePath(fromLocalURL:)` is available
            // in your Capacitor version, prefer that. As of Capacitor 5/6 the approach
            // below (constructing the _capacitor_file_ path manually) is the documented
            // fallback. Run getPath on device and confirm the WebView can fetch() the URL.
            let filePath = bundleJson.path
            let servedPath = "capacitor://localhost/_capacitor_file_\(filePath)"

            call.resolve(["path": servedPath])
        } catch {
            call.reject("Failed to locate bundle directory: \(error.localizedDescription)")
        }
    }

    @objc func list(_ call: CAPPluginCall) {
        do {
            let bundlesDir = try bundlesDirectory()
            let contents = try FileManager.default.contentsOfDirectory(
                at: bundlesDir,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles]
            )
            let legs = try contents.compactMap { url -> String? in
                let values = try url.resourceValues(forKeys: [.isDirectoryKey])
                guard values.isDirectory == true else { return nil }
                return url.lastPathComponent
            }
            call.resolve(["legs": legs])
        } catch {
            call.reject("Failed to list bundles: \(error.localizedDescription)")
        }
    }
}
