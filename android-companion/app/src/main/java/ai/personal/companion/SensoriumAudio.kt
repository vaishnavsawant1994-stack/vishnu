package ai.personal.companion

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.time.Instant
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sqrt

object SensoriumAudio {
    fun sample(context: Context, durationMs: Int = 1500): JSONObject {
        require(ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            "Microphone OS permission is not granted"
        }
        val grant = SensoriumSessionRegistry.require("microphone", "*")
        val sampleRate = 16_000
        val minBuffer = AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        require(minBuffer > 0) { "Microphone is unavailable" }
        val bufferSize = maxOf(minBuffer, sampleRate / 2)
        val recorder = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufferSize,
        )
        val boundedMs = durationMs.coerceIn(300, 2500)
        val totalSamples = sampleRate * boundedMs / 1000
        var readSamples = 0
        var squareSum = 0.0
        var crossings = 0L
        var clipped = 0L
        var previous = 0
        var speechFrames = 0
        var activeFrames = 0
        var frameCount = 0
        var speakerTurns = 0
        var inSpeech = false
        var frameRmsSum = 0.0
        var frameRmsSquareSum = 0.0
        var peakFrameRms = 0.0
        val buffer = ShortArray(minBuffer.coerceAtMost(4096).coerceAtLeast(512))
        try {
            recorder.startRecording()
            while (readSamples < totalSamples) {
                val wanted = minOf(buffer.size, totalSamples - readSamples)
                val count = recorder.read(buffer, 0, wanted)
                if (count <= 0) break
                var frameSq = 0.0
                for (i in 0 until count) {
                    val sample = buffer[i].toInt()
                    val normalized = sample / 32768.0
                    squareSum += normalized * normalized
                    frameSq += normalized * normalized
                    if ((sample >= 0) != (previous >= 0)) crossings++
                    if (abs(sample) >= 32_000) clipped++
                    previous = sample
                }
                val frameRms = sqrt(frameSq / count.coerceAtLeast(1))
                frameRmsSum += frameRms
                frameRmsSquareSum += frameRms * frameRms
                peakFrameRms = max(peakFrameRms, frameRms)
                if (frameRms > 0.010) activeFrames++
                val speaking = frameRms > 0.018
                if (speaking) speechFrames++
                if (speaking && !inSpeech) speakerTurns++
                inSpeech = speaking
                frameCount++
                readSamples += count
            }
        } finally {
            runCatching { recorder.stop() }
            recorder.release()
        }
        require(readSamples > 0) { "Microphone returned no samples" }
        val rms = sqrt(squareSum / readSamples)
        val zcr = crossings.toDouble() / readSamples.coerceAtLeast(1)
        val speechRatio = speechFrames.toDouble() / frameCount.coerceAtLeast(1)
        val activeRatio = activeFrames.toDouble() / frameCount.coerceAtLeast(1)
        val clippedFraction = clipped.toDouble() / readSamples.coerceAtLeast(1)
        val meanFrameRms = frameRmsSum / frameCount.coerceAtLeast(1)
        val variance = (frameRmsSquareSum / frameCount.coerceAtLeast(1) - meanFrameRms * meanFrameRms).coerceAtLeast(0.0)
        val energyVariation = if (meanFrameRms > 0.0001) sqrt(variance) / meanFrameRms else 0.0

        // These are deliberately conservative local acoustic cues, not identity
        // or safety-critical classifiers. Ambiguous audio stays "unknown" and
        // can be escalated to deeper reasoning only when the owner permits it.
        val label = when {
            rms < 0.004 -> "silence"
            speechRatio > 0.55 && zcr in 0.02..0.25 -> "speech_likely"
            rms > 0.08 && zcr > 0.20 && energyVariation < 0.75 -> "alarm_tone_likely"
            rms > 0.035 && zcr in 0.01..0.12 && energyVariation > 0.45 && activeRatio < 0.75 -> "doorbell_likely"
            rms > 0.015 && zcr < 0.045 && energyVariation < 0.28 && activeRatio > 0.65 -> "appliance_hum_likely"
            rms > 0.14 && zcr < 0.10 -> "mechanical_noise_likely"
            rms > 0.025 && zcr in 0.04..0.30 && activeRatio > 0.70 && speechRatio < 0.55 && energyVariation in 0.12..0.95 -> "music_likely"
            rms > 0.025 -> "ambient_noise"
            else -> "unknown"
        }
        val confidence = when (label) {
            "silence" -> 0.95
            "speech_likely" -> 0.80
            "alarm_tone_likely" -> 0.68
            "doorbell_likely" -> 0.60
            "appliance_hum_likely" -> 0.67
            "mechanical_noise_likely" -> 0.64
            "music_likely" -> 0.60
            "ambient_noise" -> 0.65
            else -> 0.40
        }
        return JSONObject()
            .put("label", label)
            .put("confidence", confidence)
            .put("rms", rms.coerceIn(0.0, 1.0))
            .put("peak_frame_rms", peakFrameRms.coerceIn(0.0, 1.0))
            .put("energy_variation", energyVariation.coerceIn(0.0, 8.0))
            .put("active_ratio", activeRatio.coerceIn(0.0, 1.0))
            .put("zero_crossing_rate", zcr.coerceIn(0.0, 1.0))
            .put("clipped_fraction", clippedFraction.coerceIn(0.0, 1.0))
            .put("speech", label == "speech_likely")
            .put("vad_active", speechRatio > 0.25)
            .put("speaker_turn_count", speakerTurns.coerceAtMost(100))
            .put("duration_ms", boundedMs)
            .put("classification_scope", "local_acoustic_cues")
            .put("raw_audio_retained", false)
            .put("local_feature_extraction", true)
            .put("resource_id", grant.resourceId)
            .put("sensor_session_id", grant.sessionId)
            .put("expires_at_epoch", grant.expiresAtMs / 1000.0)
            .put("local_consent", true)
            .put("captured_at", Instant.now().toEpochMilli() / 1000.0)
    }
}
