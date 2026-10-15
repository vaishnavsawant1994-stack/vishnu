import Foundation
import ARKit
import UIKit

@MainActor
final class SensoriumSpatialSession: NSObject, ARSessionDelegate {
    static let shared = SensoriumSpatialSession()
    private let session = ARSession()
    private var latestFrame: ARFrame?
    private(set) var active = false
    private(set) var depthEnabled = false
    private(set) var meshEnabled = false

    override init() {
        super.init()
        session.delegate = self
    }

    func inventory() -> [String: Any] {
        [
            "arkit": ARWorldTrackingConfiguration.isSupported,
            "scene_depth": ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth),
            "smoothed_scene_depth": ARWorldTrackingConfiguration.supportsFrameSemantics(.smoothedSceneDepth),
            "scene_mesh": ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh),
            "lidar_or_depth_available": ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) || ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh),
        ]
    }

    func startByOwner() throws {
        guard UIApplication.shared.applicationState == .active else {
            throw CompanionError.badResponse("Open Vishnu in the foreground to start ARKit spatial sensing.")
        }
        guard ARWorldTrackingConfiguration.isSupported else {
            throw CompanionError.badResponse("ARKit world tracking is unavailable on this device.")
        }
        stop()
        let config = ARWorldTrackingConfiguration()
        config.worldAlignment = .gravityAndHeading
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            config.frameSemantics.insert(.sceneDepth); depthEnabled = true
        } else if ARWorldTrackingConfiguration.supportsFrameSemantics(.smoothedSceneDepth) {
            config.frameSemantics.insert(.smoothedSceneDepth); depthEnabled = true
        }
        if ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh) {
            config.sceneReconstruction = .mesh; meshEnabled = true
        }
        config.planeDetection = [.horizontal, .vertical]
        session.run(config, options: [.resetTracking, .removeExistingAnchors])
        active = true
    }

    func stop() {
        if active { session.pause() }
        active = false; depthEnabled = false; meshEnabled = false; latestFrame = nil
    }

    nonisolated func session(_ session: ARSession, didUpdate frame: ARFrame) {
        Task { @MainActor in self.latestFrame = frame }
    }

    func snapshot() throws -> [String: Any] {
        guard active, let frame = latestFrame else {
            throw CompanionError.badResponse("Start the owner-approved ARKit spatial session and move the iPhone to map the environment.")
        }
        let transform = frame.camera.transform
        let position = transform.columns.3
        var anchors: [[String: Any]] = []
        if let points = frame.rawFeaturePoints {
            let count = min(points.points.count, 128)
            for index in 0..<count {
                let p = points.points[index]
                anchors.append([
                    "anchor_id": "arkit-point-\(points.identifiers[index])",
                    "label": "mapped_surface_point",
                    "position_m": ["x": Double(p.x), "y": Double(p.y), "z": Double(p.z)],
                    "confidence": 0.65,
                    "persistent": false,
                    "captured_at": frame.timestamp,
                ])
            }
        }
        for anchor in frame.anchors.prefix(128) {
            let p = anchor.transform.columns.3
            anchors.append([
                "anchor_id": anchor.identifier.uuidString,
                "label": anchor is ARPlaneAnchor ? "detected_plane" : anchor is ARMeshAnchor ? "room_mesh_anchor" : "arkit_anchor",
                "position_m": ["x": Double(p.x), "y": Double(p.y), "z": Double(p.z)],
                "confidence": 0.85,
                "persistent": false,
                "captured_at": frame.timestamp,
            ])
        }
        return [
            "tracking": String(describing: frame.camera.trackingState),
            "depth_available": depthEnabled,
            "room_mesh_available": meshEnabled,
            "camera_pose": [
                "translation_m": [Double(position.x), Double(position.y), Double(position.z)],
                "euler_angles": [Double(frame.camera.eulerAngles.x), Double(frame.camera.eulerAngles.y), Double(frame.camera.eulerAngles.z)],
            ],
            "anchors": Array(anchors.prefix(256)),
            "local_processing": true,
            "execution_authority": false,
            "captured_at": Date().timeIntervalSince1970,
        ]
    }
}
