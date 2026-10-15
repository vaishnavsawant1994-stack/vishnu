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
        var frameCount = 0
        var speakerTurns = 0
        var inSpeech = false
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
        val clippedFraction = clipped.toDouble() / readSamples.coerceAtLeast(1)
        val label = when {
            rms < 0.004 -> "silence"
            speechRatio > 0.55 && zcr in 0.02..0.25 -> "speech_likely"
            rms > 0.20 && zcr < 0.08 -> "mechanical_noise_likely"
            rms > 0.12 && zcr > 0.25 -> "alarm_tone_likely"
            rms > 0.05 && zcr in 0.08..0.25 -> "ambient_noise"
            else -> "unknown"
        }
        val confidence = when (label) {
            "silence" -> 0.95
            "speech_likely" -> 0.78
            "mechanical_noise_likely", "alarm_tone_likely" -> 0.62
            "ambient_noise" -> 0.65
            else -> 0.4
        }
        return JSONObject()
            .put("label", label)
            .put("confidence", confidence)
            .put("rms", rms.coerceIn(0.0, 1.0))
            .put("zero_crossing_rate", zcr.coerceIn(0.0, 1.0))
            .put("clipped_fraction", clippedFraction.coerceIn(0.0, 1.0))
            .put("speech", label == "speech_likely")
            .put("vad_active", speechRatio > 0.25)
            .put("speaker_turn_count", speakerTurns.coerceAtMost(100))
            .put("duration_ms", boundedMs)
            .put("raw_audio_retained", false)
            .put("local_feature_extraction", true)
            .put("resource_id", grant.resourceId)
            .put("sensor_session_id", grant.sessionId)
            .put("expires_at_epoch", grant.expiresAtMs / 1000.0)
            .put("local_consent", true)
            .put("captured_at", Instant.now().toEpochMilli() / 1000.0)
    }
}
