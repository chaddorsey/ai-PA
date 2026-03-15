// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "TimerWidget",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(name: "TimerWidget"),
    ]
)
