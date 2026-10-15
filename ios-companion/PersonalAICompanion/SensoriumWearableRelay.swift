import Foundation
import WatchConnectivity
import AVFoundation

@MainActor
final class SensoriumWearableRelay: NSObject, ObservableObject, WCSessionDelegate {
    static let shared = SensoriumWearableRelay()
    @Published private(set) var latest: [String: [String: Any]] = [:]
    @Published private(set) var activationState = "unsupported"

    private let forbiddenMediaTokens = [
        "image", "photo", "video", "frame", "base64", "pcm", "audio_bytes",
        "recording", "microphone_bytes", "camera_bytes"
    ]
    private let maxPayloadBytes = 64 * 1024

    private override init() { super.init() }

    func activate() {
        guard WCSession.isSupported() else {
            activationState = "unsupported"
            return
        }
        let session = WCSession.default
        session.delegate = self
        session.activate()
        activationState = "activating"
    }

    private func containsForbiddenMedia(_ payload: [String: Any]) -> Bool {
        payload.keys.contains { key in
            let lowered = key.lowercased()
            return forbiddenMediaTokens.contains { lowered.contains($0) }
        }
    }

    private func ingest(_ message: [String: Any], transport: String) {
        let deviceID = String((message["wearable_device_id"] as? String ?? "").prefix(200))
        guard !deviceID.isEmpty else { return }
        let wearableType = String((message["wearable_type"] as? String ?? "apple_watch").lowercased().prefix(40))
        guard ["apple_watch", "earbuds", "smart_glasses", "body_camera", "other"].contains(wearableType) else { return }
        guard let grant = SensoriumContext.shared.current("wearable", resourceID: deviceID) else { return }
        let payload = message["payload"] as? [String: Any] ?? [:]
        guard !containsForbiddenMedia(payload), JSONSerialization.isValidJSONObject(payload),
              let encoded = try? JSONSerialization.data(withJSONObject: payload), encoded.count <= maxPayloadBytes else { return }
        let confidence = min(max(message["confidence"] as? Double ?? 0.8, 0), 1)
        let capturedAt = message["captured_at"] as? Double ?? Date().timeIntervalSince1970
        latest[deviceID] = [
            "wearable_device_id": deviceID,
            "wearable_type": wearableType,
            "transport": transport,
            "payload": payload,
            "confidence": confidence,
            "captured_at": capturedAt,
            "raw_media_retained": false,
            "instruction_trust": "untrusted",
            "execution_authority": false,
            "resource_id": grant.resourceID,
            "sensor_session_id": grant.id,
            "expires_at_epoch": grant.expiresAt.timeIntervalSince1970,
            "local_consent": true,
        ]
        SensoriumLocalAudit.shared.record(
            "wearable_observation",
            sensor: "wearable",
            resourceID: deviceID,
            reason: "Semantic wearable context received via \(transport)"
        )
    }

    func inventory() -> [String: Any] {
        let watch: [String: Any]
        if WCSession.isSupported() {
            let session = WCSession.default
            watch = [
                "supported": true,
                "paired": session.isPaired,
                "watch_app_installed": session.isWatchAppInstalled,
                "reachable": session.isReachable,
                "activation_state": activationState,
                "session_required": true,
            ]
        } else {
            watch = ["supported": false, "session_required": true]
        }
        let routes = AVAudioSession.sharedInstance().currentRoute.outputs.compactMap { output -> [String: Any]? in
            let port = output.portType
            guard [AVAudioSession.Port.bluetoothA2DP, .bluetoothHFP, .bluetoothLE, .headphones].contains(port) else { return nil }
            return [
                "uid": String(output.uid.prefix(160)),
                "port_name": String(output.portName.prefix(160)),
                "port_type": port.rawValue,
                "raw_audio_accessed": false,
            ]
        }
        return [
            "apple_watch": watch,
            "earbuds": routes,
            "semantic_observations": latest.count,
            "raw_media_retained": false,
            "execution_authority": false,
            "captured_at": Date().timeIntervalSince1970,
        ]
    }

    func snapshot() throws -> [String: Any] {
        let valid = latest.values.compactMap { row -> [String: Any]? in
            guard let deviceID = row["wearable_device_id"] as? String,
                  let grant = SensoriumContext.shared.current("wearable", resourceID: deviceID) else { return nil }
            var refreshed = row
            refreshed["resource_id"] = grant.resourceID
            refreshed["sensor_session_id"] = grant.id
            refreshed["expires_at_epoch"] = grant.expiresAt.timeIntervalSince1970
            refreshed["local_consent"] = true
            return refreshed
        }
        guard SensoriumContext.shared.current("wearable") != nil || !valid.isEmpty else {
            throw CompanionError.badResponse("Start the owner-approved wearable Sensorium session first.")
        }
        var result: [String: Any] = [
            "observations": valid,
            "raw_media_retained": false,
            "execution_authority": false,
            "captured_at": Date().timeIntervalSince1970,
        ]
        if let grant = SensoriumContext.shared.current("wearable") {
            result["session"] = grant.proof
        } else if let first = valid.first,
                  let resource = first["resource_id"],
                  let sessionID = first["sensor_session_id"],
                  let expires = first["expires_at_epoch"] {
            result["session"] = [
                "sensor": "wearable",
                "resource_id": resource,
                "sensor_session_id": sessionID,
                "expires_at_epoch": expires,
                "local_consent": true,
            ]
        }
        return result
    }

    func clear() { latest.removeAll() }

    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        Task { @MainActor [weak self] in
            self?.activationState = error == nil ? String(describing: activationState) : "failed"
        }
    }

    nonisolated func sessionDidBecomeInactive(_ session: WCSession) {
        Task { @MainActor [weak self] in self?.activationState = "inactive" }
    }

    nonisolated func sessionDidDeactivate(_ session: WCSession) {
        Task { @MainActor [weak self] in
            self?.activationState = "deactivated"
            WCSession.default.activate()
        }
    }

    nonisolated func session(_ session: WCSession, didReceiveMessage message: [String : Any]) {
        Task { @MainActor [weak self] in self?.ingest(message, transport: "watch_connectivity") }
    }

    nonisolated func session(_ session: WCSession, didReceiveUserInfo userInfo: [String : Any] = [:]) {
        Task { @MainActor [weak self] in self?.ingest(userInfo, transport: "watch_connectivity") }
    }

    nonisolated func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String : Any]) {
        Task { @MainActor [weak self] in self?.ingest(applicationContext, transport: "watch_connectivity") }
    }
}
