import Foundation
import ReplayKit
import CoreMedia
import CoreImage
import UIKit
import Vision
import CryptoKit

@MainActor
final class SensoriumScreenSession {
    static let shared = SensoriumScreenSession()
    private let recorder = RPScreenRecorder.shared()
    private let ciContext = CIContext(options: [.cacheIntermediates: false])
    private var latestImage: CGImage?
    private var lastFingerprint: String?
    private(set) var active = false
    private(set) var expiresAt: Date?

    var available: Bool { recorder.isAvailable }

    func startByOwner() async throws {
        guard UIApplication.shared.applicationState == .active else {
            throw CompanionError.badResponse("Open Vishnu in the foreground to start screen understanding.")
        }
        guard recorder.isAvailable else { throw CompanionError.badResponse("ReplayKit screen capture is unavailable on this device.") }
        stop()
        recorder.isMicrophoneEnabled = false
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            recorder.startCapture(handler: { [weak self] sample, type, _ in
                guard type == .video, let pixel = CMSampleBufferGetImageBuffer(sample), let self else { return }
                let ci = CIImage(cvPixelBuffer: pixel)
                guard let cg = self.ciContext.createCGImage(ci, from: ci.extent) else { return }
                Task { @MainActor in self.latestImage = cg }
            }, completionHandler: { error in
                if let error { continuation.resume(throwing: error) }
                else { continuation.resume() }
            })
        }
        active = true
        expiresAt = Date().addingTimeInterval(5 * 60)
        Task { [weak self] in
            try? await Task.sleep(for: .seconds(5 * 60))
            guard !Task.isCancelled else { return }
            await MainActor.run { self?.stop() }
        }
    }

    func stop() {
        if recorder.isRecording || active { recorder.stopCapture { _ in } }
        active = false; expiresAt = nil; latestImage = nil; lastFingerprint = nil
    }

    private func sanitizedImage(_ cg: CGImage) -> UIImage {
        let source = UIImage(cgImage: cg)
        let maxEdge: CGFloat = 1024
        let scale = min(1, maxEdge / max(source.size.width, source.size.height))
        let size = CGSize(width: max(1, source.size.width * scale), height: max(1, source.size.height * scale))
        let renderer = UIGraphicsImageRenderer(size: size)
        return renderer.image { context in
            source.draw(in: CGRect(origin: .zero, size: size))
            context.cgContext.setFillColor(UIColor.black.cgColor)
            context.cgContext.fill(CGRect(x: 0, y: 0, width: size.width, height: size.height * 0.07))
            context.cgContext.fill(CGRect(x: 0, y: size.height * 0.94, width: size.width, height: size.height * 0.06))
        }
    }

    private func localText(_ cg: CGImage) -> String {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .fast
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        do { try handler.perform([request]) } catch { return "" }
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n").prefix(20_000).description
    }

    func snapshot() throws -> [String: Any] {
        guard active, let expiresAt, expiresAt > Date(), let cg = latestImage else {
            stop(); throw CompanionError.badResponse("Start the owner-approved ReplayKit screen session and wait for a frame first.")
        }
        let image = sanitizedImage(cg)
        guard let processedCG = image.cgImage,
              let jpeg = image.jpegData(compressionQuality: 0.68), !jpeg.isEmpty, jpeg.count <= 1_500_000 else {
            throw CompanionError.badResponse("Privacy-processed screen frame is unavailable or too large.")
        }
        let digest = SHA256.hash(data: jpeg)
        let fingerprint = digest.prefix(12).map { String(format: "%02x", $0) }.joined()
        let changed = lastFingerprint == nil || lastFingerprint != fingerprint
        lastFingerprint = fingerprint
        return [
            "mime_type": "image/jpeg",
            "base64": jpeg.base64EncodedString(),
            "width": image.size.width,
            "height": image.size.height,
            "local_text": localText(processedCG),
            "screen_fingerprint": fingerprint,
            "scene_changed": changed,
            "privacy_processed": true,
            "raw_frame_retained": false,
            "resource_id": "mobile:screen",
            "captured_at": Date().timeIntervalSince1970,
            "local_consent": true,
        ]
    }
}
