package ai.personal.companion

import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.WearableListenerService
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap

object SensoriumWearableRelay {
    const val MESSAGE_PATH = "/vishnu/sensorium/v2/observation"
    private const val MAX_MESSAGE_BYTES = 64 * 1024
    private val latest = ConcurrentHashMap<String, JSONObject>()
    private val forbiddenMediaTokens = listOf(
        "image", "photo", "video", "frame", "base64", "pcm", "audio_bytes",
        "recording", "microphone_bytes", "camera_bytes"
    )

    private fun activeGrant(resourceId: String): SensoriumSessionRegistry.Grant? =
        SensoriumSessionRegistry.get("wearable", resourceId) ?: SensoriumSessionRegistry.get("wearable", "*")

    private fun containsForbiddenMedia(payload: JSONObject): Boolean {
        val keys = payload.keys()
        while (keys.hasNext()) {
            val key = keys.next().lowercase()
            if (forbiddenMediaTokens.any { key.contains(it) }) return true
        }
        return false
    }

    fun ingest(data: ByteArray): Boolean {
        require(data.isNotEmpty() && data.size <= MAX_MESSAGE_BYTES) { "Wearable observation exceeds the size limit" }
        val message = JSONObject(data.toString(Charsets.UTF_8))
        val deviceId = message.optString("wearable_device_id").trim().take(200)
        require(deviceId.isNotBlank()) { "Wearable device ID is required" }
        val wearableType = message.optString("wearable_type", "wear_os").trim().lowercase().take(40)
        require(wearableType in setOf("wear_os", "earbuds", "smart_glasses", "body_camera", "other")) {
            "Unsupported wearable type"
        }
        val grant = activeGrant(deviceId) ?: throw SecurityException("Owner-approved wearable Sensorium session is required")
        val payload = message.optJSONObject("payload") ?: JSONObject()
        require(!containsForbiddenMedia(payload)) {
            "Raw wearable camera/audio media must use the separately governed camera or microphone path"
        }
        val payloadBytes = payload.toString().toByteArray(Charsets.UTF_8)
        require(payloadBytes.size <= MAX_MESSAGE_BYTES) { "Wearable semantic payload exceeds the size limit" }
        val confidence = message.optDouble("confidence", 0.8).coerceIn(0.0, 1.0)
        val capturedAt = message.optDouble("captured_at", System.currentTimeMillis() / 1000.0)
        latest[deviceId] = JSONObject()
            .put("wearable_device_id", deviceId)
            .put("wearable_type", wearableType)
            .put("transport", "wear_data_layer")
            .put("payload", payload)
            .put("confidence", confidence)
            .put("captured_at", capturedAt)
            .put("raw_media_retained", false)
            .put("instruction_trust", "untrusted")
            .put("execution_authority", false)
            .put("resource_id", grant.resourceId)
            .put("sensor_session_id", grant.sessionId)
            .put("expires_at_epoch", grant.expiresAtMs / 1000.0)
            .put("local_consent", true)
        return true
    }

    fun inventory(context: Context): JSONObject {
        val audio = context.getSystemService(AudioManager::class.java)
        val earbuds = JSONArray()
        audio.getDevices(AudioManager.GET_DEVICES_ALL).forEach { device ->
            if (isPersonalAudioDevice(device)) {
                earbuds.put(JSONObject()
                    .put("id", device.id)
                    .put("product_name", device.productName?.toString()?.take(160) ?: "Audio device")
                    .put("type", audioType(device.type))
                    .put("is_source", device.isSource)
                    .put("is_sink", device.isSink)
                    .put("raw_audio_accessed", false))
            }
        }
        return JSONObject()
            .put("wear_os_data_layer", JSONObject()
                .put("available", true)
                .put("message_path", MESSAGE_PATH)
                .put("session_required", true))
            .put("earbuds", earbuds)
            .put("semantic_observations", latest.size)
            .put("raw_media_retained", false)
            .put("execution_authority", false)
            .put("captured_at", System.currentTimeMillis() / 1000.0)
    }

    fun snapshot(): JSONObject {
        val rows = JSONArray()
        latest.values.sortedBy { it.optString("wearable_device_id") }.forEach { row ->
            val deviceId = row.optString("wearable_device_id")
            val grant = activeGrant(deviceId)
            if (grant != null) {
                rows.put(JSONObject(row.toString())
                    .put("resource_id", grant.resourceId)
                    .put("sensor_session_id", grant.sessionId)
                    .put("expires_at_epoch", grant.expiresAtMs / 1000.0)
                    .put("local_consent", true))
            }
        }
        val wildcard = SensoriumSessionRegistry.get("wearable", "*")
        val result = JSONObject()
            .put("observations", rows)
            .put("raw_media_retained", false)
            .put("execution_authority", false)
            .put("captured_at", System.currentTimeMillis() / 1000.0)
        if (wildcard != null) {
            result.put("session", SensoriumSessionRegistry.proof("wearable", "*"))
        } else if (rows.length() > 0) {
            val first = rows.getJSONObject(0)
            result.put("session", JSONObject()
                .put("sensor", "wearable")
                .put("resource_id", first.optString("resource_id"))
                .put("sensor_session_id", first.optString("sensor_session_id"))
                .put("expires_at_epoch", first.optDouble("expires_at_epoch"))
                .put("local_consent", true))
        }
        return result
    }

    fun clear() { latest.clear() }

    private fun isPersonalAudioDevice(device: AudioDeviceInfo): Boolean = when (device.type) {
        AudioDeviceInfo.TYPE_BLUETOOTH_A2DP,
        AudioDeviceInfo.TYPE_BLUETOOTH_SCO,
        AudioDeviceInfo.TYPE_WIRED_HEADPHONES,
        AudioDeviceInfo.TYPE_WIRED_HEADSET,
        AudioDeviceInfo.TYPE_USB_HEADSET -> true
        else -> Build.VERSION.SDK_INT >= 31 && device.type in setOf(
            AudioDeviceInfo.TYPE_BLE_HEADSET,
            AudioDeviceInfo.TYPE_BLE_SPEAKER
        )
    }

    private fun audioType(type: Int): String = when (type) {
        AudioDeviceInfo.TYPE_BLUETOOTH_A2DP -> "bluetooth_a2dp"
        AudioDeviceInfo.TYPE_BLUETOOTH_SCO -> "bluetooth_sco"
        AudioDeviceInfo.TYPE_WIRED_HEADPHONES -> "wired_headphones"
        AudioDeviceInfo.TYPE_WIRED_HEADSET -> "wired_headset"
        AudioDeviceInfo.TYPE_USB_HEADSET -> "usb_headset"
        else -> if (Build.VERSION.SDK_INT >= 31 && type == AudioDeviceInfo.TYPE_BLE_HEADSET) "ble_headset"
            else if (Build.VERSION.SDK_INT >= 31 && type == AudioDeviceInfo.TYPE_BLE_SPEAKER) "ble_speaker"
            else "other"
    }
}

class SensoriumWearableListenerService : WearableListenerService() {
    override fun onMessageReceived(messageEvent: MessageEvent) {
        if (messageEvent.path != SensoriumWearableRelay.MESSAGE_PATH) return
        runCatching { SensoriumWearableRelay.ingest(messageEvent.data) }
    }
}
