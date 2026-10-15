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
    private var activeFrames: Int = 0
    private var frames: Int = 0
    private var turns: Int = 0
    private var inSpeech = false
    private var frameRmsSum: Double = 0
    private var frameRmsSquareSum: Double = 0
    private var peakFrameRms: Double = 0
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
                self.frameRmsSum += frameRms
                self.frameRmsSquareSum += frameRms * frameRms
                self.peakFrameRms = max(self.peakFrameRms, frameRms)
                if frameRms > 0.010 { self.activeFrames += 1 }
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
        speechFrames = 0; activeFrames = 0; frames = 0; turns = 0; inSpeech = false
        frameRmsSum = 0; frameRmsSquareSum = 0; peakFrameRms = 0; startedAt = Date()
    }

    func snapshot() throws -> [String: Any] {
        guard running else { throw CompanionError.badResponse("Start the owner-approved microphone Sensorium session first.") }
        let count = max(sampleCount, 1)
        let frameCount = max(frames, 1)
        let rms = sqrt(squareSum / Double(count))
        let zcr = Double(crossings) / Double(count)
        let speechRatio = Double(speechFrames) / Double(frameCount)
        let activeRatio = Double(activeFrames) / Double(frameCount)
        let clippedFraction = Double(clipped) / Double(count)
        let meanFrameRms = frameRmsSum / Double(frameCount)
        let variance = max(0, frameRmsSquareSum / Double(frameCount) - meanFrameRms * meanFrameRms)
        let energyVariation = meanFrameRms > 0.0001 ? sqrt(variance) / meanFrameRms : 0
        let label: String
        let confidence: Double
        if rms < 0.004 {
            label = "silence"; confidence = 0.95
        } else if speechRatio > 0.55 && (0.02...0.25).contains(zcr) {
            label = "speech_likely"; confidence = 0.80
        } else if rms > 0.08 && zcr > 0.20 && energyVariation < 0.75 {
            label = "alarm_tone_likely"; confidence = 0.68
        } else if rms > 0.035 && (0.01...0.12).contains(zcr) && energyVariation > 0.45 && activeRatio < 0.75 {
            label = "doorbell_likely"; confidence = 0.60
        } else if rms > 0.015 && zcr < 0.045 && energyVariation < 0.28 && activeRatio > 0.65 {
            label = "appliance_hum_likely"; confidence = 0.67
        } else if rms > 0.14 && zcr < 0.10 {
            label = "mechanical_noise_likely"; confidence = 0.64
        } else if rms > 0.025 && (0.04...0.30).contains(zcr) && activeRatio > 0.70 && speechRatio < 0.55 && (0.12...0.95).contains(energyVariation) {
            label = "music_likely"; confidence = 0.60
        } else if rms > 0.025 {
            label = "ambient_noise"; confidence = 0.65
        } else {
            label = "unknown"; confidence = 0.40
        }
        let duration = Int(Date().timeIntervalSince(startedAt) * 1000)
        // Reset after each semantic sample so long-running sessions never build a
        // hidden audio history. Raw PCM is never copied out of the tap.
        let result: [String: Any] = [
            "label": label,
            "confidence": confidence,
            "rms": min(max(rms, 0), 1),
            "peak_frame_rms": min(max(peakFrameRms, 0), 1),
            "energy_variation": min(max(energyVariation, 0), 8),
            "active_ratio": min(max(activeRatio, 0), 1),
            "zero_crossing_rate": min(max(zcr, 0), 1),
            "clipped_fraction": min(max(clippedFraction, 0), 1),
            "speech": label == "speech_likely",
            "vad_active": speechRatio > 0.25,
            "speaker_turn_count": min(turns, 100),
            "duration_ms": min(duration, 60_000),
            "classification_scope": "local_acoustic_cues",
            "raw_audio_retained": false,
            "local_feature_extraction": true,
            "captured_at": Date().timeIntervalSince1970,
        ]
        reset()
        return result
    }
}
