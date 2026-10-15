import Foundation
import Vision
import UIKit

@MainActor
enum SensoriumVisualIntelligence {
    private static func cameraImage() async throws -> (CGImage, [String: Any]) {
        let camera = try await VisionCameraSession.shared.snapshot(privacy: ["max_edge": 1280])
        guard let encoded = camera["base64"] as? String,
              let data = Data(base64Encoded: encoded),
              let ui = UIImage(data: data),
              let cg = ui.cgImage else {
            throw CompanionError.badResponse("Privacy-processed Vision frame could not be decoded.")
        }
        return (cg, camera)
    }

    static func documentExtract() async throws -> [String: Any] {
        let grant = try SensoriumContext.shared.require("document")
        let (cg, camera) = try await cameraImage()
        let text = VNRecognizeTextRequest()
        text.recognitionLevel = .accurate
        text.usesLanguageCorrection = true
        let barcode = VNDetectBarcodesRequest()
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try handler.perform([text, barcode])
        let lines = (text.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let codes: [[String: Any]] = (barcode.results ?? []).prefix(64).map {
            ["format": $0.symbology.rawValue, "value": String(($0.payloadStringValue ?? "").prefix(4096))]
        }
        let content = String(lines.joined(separator: "\n").prefix(100_000))
        return [
            "text": content,
            "barcodes": codes,
            "fields": [:] as [String: Any],
            "handwriting": false,
            "confidence": (!content.isEmpty || !codes.isEmpty) ? 0.92 : 0.45,
            "local_extraction": true,
            "privacy_processed": true,
            "raw_image_retained": false,
            "camera_id": camera["camera_id"] as Any,
            "resource_id": grant.resourceID,
            "sensor_session_id": grant.id,
            "expires_at_epoch": grant.expiresAt.timeIntervalSince1970,
            "local_consent": true,
            "captured_at": Date().timeIntervalSince1970,
        ]
    }

    private static func point(_ point: VNRecognizedPoint?) -> [String: Any]? {
        guard let point, point.confidence >= 0.35 else { return nil }
        return ["x": point.location.x, "y": point.location.y, "confidence": point.confidence]
    }

    private static func hand(_ observation: VNHumanHandPoseObservation?) -> [String: Any]? {
        guard let observation else { return nil }
        let wrist = try? observation.recognizedPoint(.wrist)
        let index = try? observation.recognizedPoint(.indexTip)
        let thumb = try? observation.recognizedPoint(.thumbTip)
        let middle = try? observation.recognizedPoint(.middleTip)
        var row: [String: Any] = [:]
        if let p = point(wrist) { row["wrist"] = p }
        if let p = point(index) { row["index_tip"] = p }
        if let p = point(thumb) { row["thumb_tip"] = p }
        if let p = point(middle) { row["middle_tip"] = p }
        if let wrist, let index, wrist.confidence >= 0.5, index.confidence >= 0.5 {
            let dx = index.location.x - wrist.location.x
            let dy = index.location.y - wrist.location.y
            let length = max(sqrt(dx * dx + dy * dy), 0.0001)
            row["pointing_direction"] = ["x": dx / length, "y": dy / length, "confidence": min(wrist.confidence, index.confidence)]
        }
        return row.isEmpty ? nil : row
    }

    static func poseAndGesture() async throws -> [String: Any] {
        let (cg, camera) = try await cameraImage()
        let bodyRequest = VNDetectHumanBodyPoseRequest()
        let handRequest = VNDetectHumanHandPoseRequest()
        handRequest.maximumHandCount = 2
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try handler.perform([bodyRequest, handRequest])
        var body: [String: Any] = [:]
        if let observation = bodyRequest.results?.first {
            let joints: [(String, VNHumanBodyPoseObservation.JointName)] = [
                ("left_shoulder", .leftShoulder), ("right_shoulder", .rightShoulder),
                ("left_elbow", .leftElbow), ("right_elbow", .rightElbow),
                ("left_wrist", .leftWrist), ("right_wrist", .rightWrist),
                ("left_hip", .leftHip), ("right_hip", .rightHip),
                ("left_knee", .leftKnee), ("right_knee", .rightKnee),
                ("left_ankle", .leftAnkle), ("right_ankle", .rightAnkle),
            ]
            for (name, joint) in joints {
                if let recognized = try? observation.recognizedPoint(joint), let p = point(recognized) { body[name] = p }
            }
        }
        let hands = (handRequest.results ?? []).compactMap { hand($0) }
        return [
            "body_pose_detected": !body.isEmpty,
            "body_landmarks": body,
            "hands": hands,
            "gesture_pointing_detected": hands.contains { $0["pointing_direction"] != nil },
            "camera_id": camera["camera_id"] as Any,
            "local_processing": true,
            "privacy_processed": true,
            "raw_frame_retained": false,
            "execution_authority": false,
            "captured_at": Date().timeIntervalSince1970,
        ]
    }
}
