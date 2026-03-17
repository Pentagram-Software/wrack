// swift-tools-version:5.7
import PackageDescription

let package = Package(
    name: "VideoProtocol",
    platforms: [
        .iOS(.v16),
        .macOS(.v13),
    ],
    products: [
        .library(name: "VideoProtocol", targets: ["VideoProtocol"]),
    ],
    targets: [
        .target(name: "VideoProtocol"),
        .testTarget(
            name: "VideoProtocolTests",
            dependencies: ["VideoProtocol"]
        ),
    ]
)
