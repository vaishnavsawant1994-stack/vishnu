import AVFoundation
import UIKit
import Vision

private final class VisionPhotoDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    let completion: (Result<Data, Error>) -> Void
    init(completion: @escaping (Result<Data, Error>) -> Void) { self.completion = completion }
    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        if let error { completion(.failure(error)); return }
        guard let data = photo.fileDataRepresentation() else {
            completion(.failure(CompanionError.badResponse("Camera returned no image data.")))
            return
        }
        completion(.success(data))
    }
}

@MainActor
final class VisionCameraSession {
    static let shared = VisionCameraSession()
    static let minLiveBatteryPercent = 15
    private let session = AVCaptureSession()
    private let output = AVCapturePhotoOutput()
    private var facing = "front"
    private var cameraID = "mobile:front"
    private var sensorSessionID: String?
    private var expiresAt: Date?
    private var expiryTask: Task<Void, Never>?
    private var pendingDelegate: VisionPhotoDelegate?
    private var observers: [NSObjectProtocol] = []
    private(set) var active = false

    init() {
        UIDevice.current.isBatteryMonitoringEnabled = true
        let center = NotificationCenter.default
        observers.append(center.addObserver(forName: UIApplication.didEnterBackgroundNotification, object: nil, queue: .main) { _ in
            Task { @MainActor in VisionCameraSession.shared.stop() }
        })
        observers.append(center.addObserver(forName: UIApplication.willResignActiveNotification, object: nil, queue: .main) { _ in
            Task { @MainActor in VisionCameraSession.shared.stop() }
        })
    }

    static func cameras() -> [[String: Any]] {
        AVCaptureDevice.devices(for: .video).prefix(32).map { device in
            let facing: String
            switch device.position {
            case .front: facing = "front"
            case .back: facing = "back"
            case .unspecified: facing = "external"
            @unknown default: facing = "unknown"
            }
            return [
                "camera_id": "mobile:\(device.uniqueID)",
                "label": device.localizedName,
                "facing": facing,
                "external": device.position == .unspecified,
            ]
        }
    }

    var permissionDescription: String {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: return "granted"
        case .denied: return "denied"
        case .restricted: return "restricted"
        case .notDetermined: return "undetermined"
        @unknown default: return "unknown"
        }
    }

    var remainingSeconds: Int {
        guard active, let expiresAt else { return 0 }
        return max(0, Int(ceil(expiresAt.timeIntervalSinceNow)))
    }

    var batteryPercent: Int {
        let level = UIDevice.current.batteryLevel
        return level < 0 ? -1 : max(0, min(100, Int((level * 100).rounded())))
    }

    func status() -> [String: Any] {
        if let expiresAt, expiresAt <= Date() { stop() }
        return [
            "active": active,
            "permission": permissionDescription,
            "foreground_required": true,
            "facing": facing,
            "camera_id": cameraID,
            "sensor_session_id": active ? (sensorSessionID ?? NSNull()) : NSNull(),
            "expires_at": expiresAt.map(Self.iso) ?? NSNull(),
            "remaining_seconds": remainingSeconds,
            "battery_percent": batteryPercent,
            "min_live_battery_percent": Self.minLiveBatteryPercent,
            "consent_required": !active,
        ]
    }

    private static func resolveCamera(cameraID requestedID: String?, facing requestedFacing: String) -> AVCaptureDevice? {
        if let requestedID, requestedID.hasPrefix("mobile:"), !["mobile:front", "mobile:back", "mobile:auto"].contains(requestedID) {
            let hardwareID = String(requestedID.dropFirst("mobile:".count))
            if let exact = AVCaptureDevice.devices(for: .video).first(where: { $0.uniqueID == hardwareID }) { return exact }
        }
        let position: AVCaptureDevice.Position = requestedFacing.lowercased() == "back" ? .back : .front
        return AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: position)
    }

    func startByOwner(facing requestedFacing: String = "front", cameraID requestedID: String? = nil) async throws {
        guard UIApplication.shared.applicationState == .active else {
            throw CompanionError.badResponse("Open Vishnu in the foreground to start Vision.")
        }
        let authorization = AVCaptureDevice.authorizationStatus(for: .video)
        if authorization == .notDetermined {
            let granted = await AVCaptureDevice.requestAccess(for: .video)
            guard granted else { throw CompanionError.badResponse("Camera permission denied.") }
        }
        guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
            throw CompanionError.badResponse("Camera permission is not available.")
        }
        let battery = batteryPercent
        if battery >= 0 && battery < Self.minLiveBatteryPercent {
            throw CompanionError.badResponse("Vishnu Vision needs at least \(Self.minLiveBatteryPercent)% battery to start.")
        }
        stop()
        facing = requestedFacing.lowercased() == "back" ? "back" : "front"
        session.beginConfiguration()
        session.sessionPreset = .photo
        defer { session.commitConfiguration() }
        guard let camera = Self.resolveCamera(cameraID: requestedID, facing: facing) else {
            throw CompanionError.badResponse("Requested camera is unavailable.")
        }
        facing = camera.position == .back ? "back" : (camera.position == .front ? "front" : "external")
        cameraID = "mobile:\(camera.uniqueID)"
        let input = try AVCaptureDeviceInput(device: camera)
        guard session.canAddInput(input), session.canAddOutput(output) else {
            throw CompanionError.badResponse("Camera could not be configured.")
        }
        session.addInput(input)
        session.addOutput(output)
        session.startRunning()
        active = true
        sensorSessionID = UUID().uuidString
        expiresAt = Date().addingTimeInterval(5 * 60)
        expiryTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(5 * 60))
            guard !Task.isCancelled else { return }
            await MainActor.run { self?.stop() }
        }
    }

    func stop() {
        expiryTask?.cancel()
        expiryTask = nil
        expiresAt = nil
        active = false
        sensorSessionID = nil
        pendingDelegate = nil
        if session.isRunning { session.stopRunning() }
        session.beginConfiguration()
        session.inputs.forEach { session.removeInput($0) }
        session.outputs.forEach { session.removeOutput($0) }
        session.commitConfiguration()
    }

    private static func normalizedImage(_ image: UIImage) -> UIImage {
        if image.imageOrientation == .up { return image }
        let renderer = UIGraphicsImageRenderer(size: image.size)
        return renderer.image { _ in image.draw(in: CGRect(origin: .zero, size: image.size)) }
    }

    private static func rect(_ object: [String: Any], size: CGSize) throws -> CGRect {
        let x = (object["x"] as? NSNumber)?.doubleValue ?? 0
        let y = (object["y"] as? NSNumber)?.doubleValue ?? 0
        let width = (object["width"] as? NSNumber)?.doubleValue ?? 0
        let height = (object["height"] as? NSNumber)?.doubleValue ?? 0
        guard x >= 0, y >= 0, width > 0, height > 0, x + width <= 1.000001, y + height <= 1.000001 else {
            throw CompanionError.badResponse("Invalid privacy region.")
        }
        return CGRect(x: x * size.width, y: y * size.height, width: width * size.width, height: height * size.height).integral
    }

    private static func pixelated(_ image: UIImage, rect: CGRect) -> UIImage {
        guard let cg = image.cgImage,
              let crop = cg.cropping(to: CGRect(x: rect.minX, y: image.size.height - rect.maxY, width: rect.width, height: rect.height)) else { return image }
        let tinySize = CGSize(width: max(1, rect.width / 20), height: max(1, rect.height / 20))
        let tiny = UIGraphicsImageRenderer(size: tinySize).image { context in
            context.cgContext.interpolationQuality = .none
            UIImage(cgImage: crop).draw(in: CGRect(origin: .zero, size: tinySize))
        }
        let renderer = UIGraphicsImageRenderer(size: image.size)
        return renderer.image { context in
            image.draw(at: .zero)
            context.cgContext.interpolationQuality = .none
            tiny.draw(in: rect)
        }
    }

    private static func faceRects(_ image: UIImage) -> [CGRect] {
        guard let cg = image.cgImage else { return [] }
        let request = VNDetectFaceRectanglesRequest()
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        do { try handler.perform([request]) } catch { return [] }
        return (request.results ?? []).prefix(32).map { face in
            let box = face.boundingBox
            return CGRect(
                x: box.minX * image.size.width,
                y: (1 - box.maxY) * image.size.height,
                width: box.width * image.size.width,
                height: box.height * image.size.height
            ).insetBy(dx: -box.width * image.size.width * 0.25, dy: -box.height * image.size.height * 0.25)
        }
    }

    private static func privacyProcess(_ data: Data, privacy: [String: Any]) throws -> (Data, [String: Any]) {
        guard let source = UIImage(data: data) else { throw CompanionError.badResponse("Camera snapshot could not be decoded.") }
        var image = normalizedImage(source)
        let original = image.size
        if let crop = privacy["crop"] as? [String: Any] {
            let cropRect = try rect(crop, size: image.size)
            guard let cg = image.cgImage?.cropping(to: CGRect(x: cropRect.minX, y: image.size.height - cropRect.maxY, width: cropRect.width, height: cropRect.height)) else {
                throw CompanionError.badResponse("Camera crop failed.")
            }
            image = UIImage(cgImage: cg)
        }
        let regions = (privacy["redact_regions"] as? [[String: Any]]) ?? []
        for item in regions.prefix(64) { image = pixelated(image, rect: try rect(item, size: image.size)) }
        let requireFaces = (privacy["require_face_redaction"] as? Bool) ?? false
        var faceCount = 0
        if requireFaces {
            let faces = faceRects(image); faceCount = faces.count
            for face in faces { image = pixelated(image, rect: face.intersection(CGRect(origin: .zero, size: image.size))) }
        }
        let maxEdge = min(1280, max(64, (privacy["max_edge"] as? NSNumber)?.intValue ?? 1024))
        if max(image.size.width, image.size.height) > CGFloat(maxEdge) {
            let scale = CGFloat(maxEdge) / max(image.size.width, image.size.height)
            let size = CGSize(width: max(1, image.size.width * scale), height: max(1, image.size.height * scale))
            image = UIGraphicsImageRenderer(size: size).image { _ in image.draw(in: CGRect(origin: .zero, size: size)) }
        }
        guard let processed = image.jpegData(compressionQuality: 0.68), !processed.isEmpty, processed.count <= 1_500_000 else {
            throw CompanionError.badResponse("Privacy-processed camera snapshot is too large.")
        }
        return (processed, [
            "original_width": Int(original.width), "original_height": Int(original.height),
            "width": Int(image.size.width), "height": Int(image.size.height),
            "redacted_regions": min(regions.count, 64),
            "faces_processed": requireFaces, "faces_detected": faceCount,
            "privacy_processed": true,
        ])
    }

    func snapshot(privacy: [String: Any] = [:]) async throws -> [String: Any] {
        guard active, let expiresAt, expiresAt > Date(), UIApplication.shared.applicationState == .active,
              let sensorSessionID else {
            stop()
            throw CompanionError.badResponse("Enable Vishnu Vision in the foreground before requesting a snapshot.")
        }
        let battery = batteryPercent
        if battery >= 0 && battery < Self.minLiveBatteryPercent {
            stop()
            throw CompanionError.badResponse("Vishnu Vision stopped because battery is below \(Self.minLiveBatteryPercent)%.")
        }
        let data: Data = try await withCheckedThrowingContinuation { continuation in
            let delegate = VisionPhotoDelegate { result in continuation.resume(with: result) }
            pendingDelegate = delegate
            output.capturePhoto(with: AVCapturePhotoSettings(), delegate: delegate)
        }
        pendingDelegate = nil
        guard !data.isEmpty, data.count <= 4_000_000 else {
            throw CompanionError.badResponse("Camera snapshot is empty or too large.")
        }
        let (processed, privacyMetadata) = try Self.privacyProcess(data, privacy: privacy)
        return [
            "mime_type": "image/jpeg",
            "base64": processed.base64EncodedString(),
            "width": privacyMetadata["width"] ?? 0,
            "height": privacyMetadata["height"] ?? 0,
            "facing": facing,
            "camera_id": cameraID,
            "sensor_session_id": sensorSessionID,
            "privacy": privacyMetadata,
            "battery_percent": battery,
            "min_live_battery_percent": Self.minLiveBatteryPercent,
            "captured_at": Self.iso(Date()),
        ]
    }

    private static func iso(_ date: Date) -> String { ISO8601DateFormatter().string(from: date) }
}
