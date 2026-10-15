import Foundation
import AVFoundation

@MainActor
final class SensoriumAudioFeatures {
    static let shared = SensoriumAudioFeatures()
    private let engine = AVAudioEngine()
    private var running = false
    private var squareSum: Double = 0
    private var sampleCount: Int = 0
    private var crossings: Int = 0
    private var clipped: Int = 0
    private var previous: Float = 0
    private var speechFrames: Int = 0
    private var frames: Int = 0
    private var turns: Int = 0
    private var inSpeech = false
    private var startedAt = Date()

    static var permissionDescription: String {
        switch AVAudioSession.sharedInstance().recordPermission {
        case .granted: return "granted"
        case .denied: return "denied"
        case .undetermined: return "undetermined"
        @unknown default: return "unknown"
        }
    }

    func start() throws {
        if running { return }
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.record, mode: .measurement, options: [.duckOthers])
        try session.setActive(true)
        reset()
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            guard let channel = buffer.floatChannelData?.pointee else { return }
            let count = Int(buffer.frameLength)
            var frameSq: Double = 0
            var localCrossings = 0
            var localClipped = 0
            var prior: Float = 0
            for index in 0..<count {
                let value = channel[index]
                frameSq += Double(value * value)
                if (value >= 0) != (prior >= 0) { localCrossings += 1 }
                if abs(value) >= 0.98 { localClipped += 1 }
                prior = value
            }
            let frameRms = count > 0 ? sqrt(frameSq / Double(count)) : 0
            let speech = frameRms > 0.018
            Task { @MainActor in
                guard let self, self.running else { return }
                self.squareSum += frameSq
                self.sampleCount += count
                self.crossings += localCrossings
                self.clipped += localClipped
                if speech { self.speechFrames += 1 }
                if speech && !self.inSpeech { self.turns += 1 }
                self.inSpeech = speech
                self.frames += 1
                self.previous = prior
            }
        }
        engine.prepare()
        try engine.start()
        running = true
    }

    func stop() {
        if running {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
            try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
        }
        running = false
        reset()
    }

    private func reset() {
        squareSum = 0; sampleCount = 0; crossings = 0; clipped = 0; previous = 0
        speechFrames = 0; frames = 0; turns = 0; inSpeech = false; startedAt = Date()
    }

    func snapshot() throws -> [String: Any] {
        guard running else { throw CompanionError.badResponse("Start the owner-approved microphone Sensorium session first.") }
        let count = max(sampleCount, 1)
        let rms = sqrt(squareSum / Double(count))
        let zcr = Double(crossings) / Double(count)
        let speechRatio = Double(speechFrames) / Double(max(frames, 1))
        let clippedFraction = Double(clipped) / Double(count)
        let label: String
        let confidence: Double
        if rms < 0.004 { label = "silence"; confidence = 0.95 }
        else if speechRatio > 0.55 && (0.02...0.25).contains(zcr) { label = "speech_likely"; confidence = 0.78 }
        else if rms > 0.20 && zcr < 0.08 { label = "mechanical_noise_likely"; confidence = 0.62 }
        else if rms > 0.12 && zcr > 0.25 { label = "alarm_tone_likely"; confidence = 0.62 }
        else if rms > 0.05 { label = "ambient_noise"; confidence = 0.65 }
        else { label = "unknown"; confidence = 0.4 }
        let duration = Int(Date().timeIntervalSince(startedAt) * 1000)
        // Reset after each semantic sample so long-running sessions never build a
        // hidden audio history. Raw PCM is never copied out of the tap.
        let result: [String: Any] = [
            "label": label,
            "confidence": confidence,
            "rms": min(max(rms, 0), 1),
            "zero_crossing_rate": min(max(zcr, 0), 1),
            "clipped_fraction": min(max(clippedFraction, 0), 1),
            "speech": label == "speech_likely",
            "vad_active": speechRatio > 0.25,
            "speaker_turn_count": min(turns, 100),
            "duration_ms": min(duration, 60_000),
            "raw_audio_retained": false,
            "local_feature_extraction": true,
            "captured_at": Date().timeIntervalSince1970,
        ]
        reset()
        return result
    }
}
