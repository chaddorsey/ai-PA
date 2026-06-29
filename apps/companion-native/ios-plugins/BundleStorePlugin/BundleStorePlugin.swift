// BundleStorePlugin.swift
// Amtrak Companion — Plan 3: BundleStore Capacitor plugin
//
// Stores audio bundles in applicationSupportDirectory — iOS does NOT evict this
// directory on low storage (unlike NSCachesDirectory or NSTemporaryDirectory).
// Bundle layout: .../Application Support/amtrak-bundles/<legId>/  (unzipped content)
//
// UNZIP: Uses Apple's Compression framework (via libcompression) directly — NOT
// Process() / /usr/bin/unzip which is unavailable on iOS app sandboxes.
// Alternatively, adopt the ZIPFoundation Swift package (add via Swift Package Manager).
// This implementation uses ZIPFoundation for its straightforward API.
// Add to your Podfile/SPM:  .package(url: "https://github.com/weichsel/ZIPFoundation.git", from: "0.9.19")
//
// IDEMPOTENT: skips download if bundle.json already exists in the leg directory.
// BOOT SCAN: load() scans applicationSupportDirectory and populates legRegistry so
// getPath/list work immediately on app restart without re-downloading.
//
// DEVICE BUILD: Add to App Xcode target + add ZIPFoundation via Swift Package Manager.
// WRITTEN, NOT COMPILED HERE. User must build on Mac with Xcode 15+.

import Foundation
import Capacitor
import ZIPFoundation   // Swift Package: https://github.com/weichsel/ZIPFoundation

@objc(BundleStorePlugin)
public class BundleStorePlugin: CAPPlugin {

    // MARK: - Properties

    // Absolute path to the root bundles directory (created on first access).
    private var bundlesRoot: URL {
        let appSupport = FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first!
        let dir = appSupport.appendingPathComponent("amtrak-bundles", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    // In-memory registry of legId → absolute path (populated on boot scan + after download).
    private var legRegistry: [String: URL] = [:]
    private let registryLock = NSLock()

    // MARK: - Plugin lifecycle: boot scan

    public override func load() {
        // Populate legRegistry from disk so getPath/list work immediately on restart.
        scanBundlesRoot()
    }

    private func scanBundlesRoot() {
        let fm = FileManager.default
        guard let contents = try? fm.contentsOfDirectory(at: bundlesRoot,
                                                          includingPropertiesForKeys: [.isDirectoryKey]) else {
            return
        }
        registryLock.lock()
        defer { registryLock.unlock() }
        for url in contents {
            var isDir: ObjCBool = false
            let bundleJson = url.appendingPathComponent("bundle.json")
            if fm.fileExists(atPath: url.path, isDirectory: &isDir),
               isDir.boolValue,
               fm.fileExists(atPath: bundleJson.path) {
                legRegistry[url.lastPathComponent] = url
            }
        }
    }

    // MARK: - download

    @objc func download(_ call: CAPPluginCall) {
        guard let legId = call.getString("legId"),
              let urlStr = call.getString("url"),
              let sourceURL = URL(string: urlStr) else {
            call.reject("Missing or invalid legId / url")
            return
        }

        let destDir = bundlesRoot.appendingPathComponent(legId, isDirectory: true)
        let bundleJson = destDir.appendingPathComponent("bundle.json")

        // Idempotent: already downloaded.
        if FileManager.default.fileExists(atPath: bundleJson.path) {
            call.resolve()
            return
        }

        let task = URLSession.shared.downloadTask(with: sourceURL) { [weak self] tempURL, _, error in
            guard let self else { return }

            if let error = error {
                call.reject("Download failed: \(error.localizedDescription)")
                return
            }
            guard let tempURL = tempURL else {
                call.reject("No temporary file returned by URLSession")
                return
            }

            do {
                let fm = FileManager.default
                try fm.createDirectory(at: destDir, withIntermediateDirectories: true)

                let zipDest = destDir.appendingPathComponent("bundle.zip")
                if fm.fileExists(atPath: zipDest.path) {
                    try fm.removeItem(at: zipDest)
                }
                try fm.moveItem(at: tempURL, to: zipDest)

                // Unzip with ZIPFoundation (NOT /usr/bin/unzip — unavailable on iOS).
                try fm.unzipItem(at: zipDest, to: destDir)

                // Remove the zip after successful extraction.
                try? fm.removeItem(at: zipDest)

                // Register in memory.
                self.registryLock.lock()
                self.legRegistry[legId] = destDir
                self.registryLock.unlock()

                call.resolve()
            } catch {
                call.reject("Unzip/move failed: \(error.localizedDescription)")
            }
        }
        task.resume()
    }

    // MARK: - getPath

    @objc func getPath(_ call: CAPPluginCall) {
        guard let legId = call.getString("legId") else {
            call.reject("Missing legId")
            return
        }

        registryLock.lock()
        let url = legRegistry[legId]
        registryLock.unlock()

        if let url = url {
            call.resolve(["path": url.path])
        } else {
            // Fall back to computing the path if the registry missed it (e.g., just unzipped).
            let computed = bundlesRoot.appendingPathComponent(legId, isDirectory: true)
            if FileManager.default.fileExists(atPath: computed.appendingPathComponent("bundle.json").path) {
                registryLock.lock()
                legRegistry[legId] = computed
                registryLock.unlock()
                call.resolve(["path": computed.path])
            } else {
                call.reject("Leg bundle not found for legId: \(legId). Call download() first.")
            }
        }
    }

    // MARK: - list

    @objc func list(_ call: CAPPluginCall) {
        registryLock.lock()
        let legs = Array(legRegistry.keys)
        registryLock.unlock()
        call.resolve(["legs": legs])
    }
}
