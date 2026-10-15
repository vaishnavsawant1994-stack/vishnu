import Foundation
import UIKit
import UserNotifications

@MainActor
final class SensoriumCompanionBridge {
    static let shared = SensoriumCompanionBridge()
    private weak var store: CompanionStore?
    private var previousHandler: (([String: Any]) async -> [String: Any])?
    private var previousStatus: ((String, Bool) -> Void)?

    private let capabilities = [
        "device_info", "battery", "notification", "open_url", "launch_app", "voice_status",
        "camera_list", "camera_status", "camera_session_start", "camera_snapshot", "camera_session_stop",
        "sensor_inventory", "sensor_session_start", "sensor_snapshot", "sensor_stop_all",
        "screen_snapshot", "audio_event_sample", "document_extract", "pose_gesture", "spatial_snapshot",
        "data_plane_status", "data_plane_progress_put", "data_plane_progress_get", "data_plane_tombstone",
        "data_plane_progress_pending", "data_plane_progress_ack",
    ]

    func install(on companion: CompanionStore) {
        store = companion
        previousHandler = companion.socket.commandHandler
        previousStatus = companion.socket.onStatus
        companion.socket.commandHandler = { [weak self] message in
            guard let self else { return ["ok": false, "error": "Sensorium bridge unavailable"] }
            if self.handles(message["action"] as? String ?? "") { return await self.handle(message) }
            if let previous = self.previousHandler { return await previous(message) }
            return ["ok": false, "error": "Unsupported iOS action"]
        }
        companion.socket.onStatus = { [weak self, weak companion] text, connected in
            self?.previousStatus?(text, connected)
            if !connected { SensoriumContext.shared.stopAll() }
            if connected, let device = companion?.deviceID {
                Task { await companion?.socket.send(["type": "hello", "device_id": device, "platform": "ios", "capabilities": self?.capabilities ?? []]) }
            }
        }
    }

    private func handles(_ action: String) -> Bool {
        ["sensor_inventory", "sensor_session_start", "sensor_snapshot", "sensor_stop_all", "screen_snapshot", "audio_event_sample", "document_extract", "pose_gesture", "spatial_snapshot"].contains(action)
    }

    private func resource(for sensor: String, requested: String) -> String {
        if requested != "*" { return requested }
        if sensor == "screen" { return "mobile:screen" }
        if sensor == "spatial" { return "mobile:spatial" }
        return "*"
    }

    private func notifyConsent(sensor: String, reason: String) async {
        let content = UNMutableNotificationContent()
        content.title = "Vishnu requests \(sensor)"
        content.body = String(reason.prefix(180)) + " Open Vishnu to review and allow this session."
        content.sound = .default
        try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "sensorium-\(sensor)-\(UUID().uuidString)", content: content, trigger: nil))
    }

    private func sessionRequest(_ params: [String: Any]) async -> [String: Any] {
        let sensorRaw = (params["sensor"] as? String ?? "").lowercased()
        let sensor = sensorRaw == "audio" ? "microphone" : sensorRaw
        guard !sensor.isEmpty else { return ["ok": false, "error": "Sensor is required"] }
        let requested = params["resource_id"] as? String ?? "*"
        let resolved = resource(for: sensor, requested: requested)
        if let grant = SensoriumContext.shared.current(sensor, resourceID: resolved) {
            return ["ok": true, "result": grant.proof.merging(["active": true, "consent_required": false], uniquingKeysWith: { _, new in new })]
        }
        let reason = params["reason"] as? String ?? "Vishnu needs temporary \(sensor) context for your request."
        await notifyConsent(sensor: sensor, reason: reason)
        return [
            "ok": true,
            "result": [
                "sensor": sensor,
                "resource_id": resolved,
                "active": false,
                "consent_required": true,
                "foreground_required": true,
                "instruction": "Open Vishnu > Sensorium Privacy and choose Allow this session for \(sensor). Remote requests cannot arm iPhone sensors.",
            ],
        ]
    }

    private func handle(_ message: [String: Any]) async -> [String: Any] {
        let action = message["action"] as? String ?? ""
        let params = message["parameters"] as? [String: Any] ?? [:]
        do {
            switch action {
            case "sensor_inventory":
                return ["ok": true, "result": SensoriumContext.shared.inventory()]
            case "sensor_session_start":
                return await sessionRequest(params)
            case "sensor_snapshot":
                let requested = params["sensors"] as? [String] ?? []
                return ["ok": true, "result": try SensoriumContext.shared.snapshot(requested)]
            case "screen_snapshot":
                let grant = try SensoriumContext.shared.require("screen", resourceID: "mobile:screen")
                var result = try SensoriumScreenSession.shared.snapshot()
                result["sensor_session_id"] = grant.id
                result["expires_at_epoch"] = grant.expiresAt.timeIntervalSince1970
                result["local_consent"] = true
                return ["ok": true, "result": result]
            case "audio_event_sample":
                let grant = try SensoriumContext.shared.require("microphone")
                var result = try SensoriumAudioFeatures.shared.snapshot()
                result["resource_id"] = grant.resourceID
                result["sensor_session_id"] = grant.id
                result["expires_at_epoch"] = grant.expiresAt.timeIntervalSince1970
                result["local_consent"] = true
                return ["ok": true, "result": result]
            case "document_extract":
                return ["ok": true, "result": try await SensoriumVisualIntelligence.documentExtract()]
            case "pose_gesture":
                return ["ok": true, "result": try await SensoriumVisualIntelligence.poseAndGesture()]
            case "spatial_snapshot":
                let grant = try SensoriumContext.shared.require("spatial", resourceID: "mobile:spatial")
                var result = try SensoriumSpatialSession.shared.snapshot()
                result["resource_id"] = grant.resourceID
                result["sensor_session_id"] = grant.id
                result["expires_at_epoch"] = grant.expiresAt.timeIntervalSince1970
                result["local_consent"] = true
                return ["ok": true, "result": result]
            case "sensor_stop_all":
                SensoriumContext.shared.stopAll()
                SensoriumAudioFeatures.shared.stop()
                store?.vision.stop(); store?.visionActive = false
                store?.voice.deactivate(); store?.voiceActive = false
                return ["ok": true, "result": ["stopped": true, "sessions_revoked": true]]
            default:
                return ["ok": false, "error": "Unsupported Sensorium action"]
            }
        } catch {
            return ["ok": false, "error": error.localizedDescription]
        }
    }
}
