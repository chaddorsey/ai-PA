// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "CapacitorBundleStore",
    platforms: [.iOS(.v13)],
    products: [
        .library(
            name: "CapacitorBundleStore",
            targets: ["BundleStorePlugin"])
    ],
    dependencies: [
        .package(url: "https://github.com/ionic-team/capacitor-swift-pm.git", branch: "main"),
        .package(url: "https://github.com/weichsel/ZIPFoundation.git", .upToNextMajor(from: "0.9.0"))
    ],
    targets: [
        .target(
            name: "BundleStorePlugin",
            dependencies: [
                .product(name: "Capacitor", package: "capacitor-swift-pm"),
                .product(name: "Cordova", package: "capacitor-swift-pm"),
                .product(name: "ZIPFoundation", package: "ZIPFoundation")
            ],
            path: "ios/Sources/BundleStorePlugin")
    ]
)
