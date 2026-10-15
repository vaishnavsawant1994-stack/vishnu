import AVFoundation
import UIKit

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
    private let session = AVCaptureSession()
    private let output = AVCapturePhotoOutput()
    private var facing = "front"
    private var expiresAt: Date?
    private var expiryTask: Task<Void, Never>?
    private var pendingDelegate: VisionPhotoDelegate?
    private var observers: [NSObjectProtocol] = []
    private(set) var active = false

    init() {
        let center = NotificationCenter.default
        observers.append(center.addObserver(forName: UIApplication.didEnterBackgroundNotification, object: nil, queue: .main) { _ in
            Task { @MainActor in VisionCameraSession.shared.stop() }
        })
        observers.append(center.addObserver(forName: UIApplication.willResignActiveNotification, object: nil, queue: .main) { _ in
            Task { @MainActor in VisionCameraSession.shared.stop() }
        })
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

    func status() -> [String: Any] {
        if let expiresAt, expiresAt <= Date() { stop() }
        return [
            "active": active,
            "permission": permissionDescription,
            "foreground_required": true,
            "facing": facing,
            "expires_at": expiresAt.map(Self.iso) ?? NSNull(),
            "consent_required": !active
        ]
    }

    func startByOwner(facing requestedFacing: String = "front") async throws {
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
        stop()
        facing = requestedFacing.lowercased() == "back" ? "back" : "front"
        session.beginConfiguration()
        session.sessionPreset = .photo
        defer { session.commitConfiguration() }
        let position: AVCaptureDevice.Position = facing == "back" ? .back : .front
        guard let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: position) else {
            throw CompanionError.badResponse("Requested camera is unavailable.")
        }
        let input = try AVCaptureDeviceInput(device: camera)
        guard session.canAddInput(input), session.canAddOutput(output) else {
            throw CompanionError.badResponse("Camera could not be configured.")
        }
        session.addInput(input)
        session.addOutput(output)
        session.startRunning()
        active = true
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
        pendingDelegate = nil
        if session.isRunning { session.stopRunning() }
        session.beginConfiguration()
        session.inputs.forEach { session.removeInput($0) }
        session.outputs.forEach { session.removeOutput($0) }
        session.commitConfiguration()
    }

    func snapshot() async throws -> [String: Any] {
        guard active, let expiresAt, expiresAt > Date(), UIApplication.shared.applicationState == .active else {
            stop()
            throw CompanionError.badResponse("Enable Vishnu Vision in the foreground before requesting a snapshot.")
        }
        let data: Data = try await withCheckedThrowingContinuation { continuation in
            let delegate = VisionPhotoDelegate { result in continuation.resume(with: result) }
            pendingDelegate = delegate
            output.capturePhoto(with: AVCapturePhotoSettings(), delegate: delegate)
        }
        pendingDelegate = nil
        guard !data.isEmpty, data.count <= 1_500_000 else {
            throw CompanionError.badResponse("Camera snapshot is empty or too large.")
        }
        let image = UIImage(data: data)
        return [
            "mime_type": "image/jpeg",
            "base64": data.base64EncodedString(),
            "width": Int(image?.size.width ?? 0),
            "height": Int(image?.size.height ?? 0),
            "facing": facing,
            "captured_at": Self.iso(Date())
        ]
    }

    private static func iso(_ date: Date) -> String {
        ISO8601DateFormatter().string(from: date)
    }
}
