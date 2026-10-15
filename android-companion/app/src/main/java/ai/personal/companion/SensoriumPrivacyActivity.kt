package ai.personal.companion

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.text.DateFormat
import java.util.Date

class SensoriumPrivacyActivity : AppCompatActivity() {
    private lateinit var list: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(28, 32, 28, 32) }
        root.addView(TextView(this).apply { text = "Sensorium Privacy"; textSize = 24f })
        root.addView(TextView(this).apply {
            text = "Every sensor is session-only. This screen shows local active grants. Seeing/hearing never grants Computer Control, Device Control, IoT or tool authority."
            textSize = 14f
        })
        val refresh = Button(this).apply { text = "Refresh sensor status"; setOnClickListener { render() } }
        val stop = Button(this).apply { text = "STOP ALL SENSING"; setOnClickListener { stopAll(); render() } }
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(refresh); root.addView(stop); root.addView(list)
        setContentView(ScrollView(this).apply { addView(root) })
        render()
    }

    private fun heading(value: String) = TextView(this).apply {
        text = value
        textSize = 18f
        setPadding(0, 22, 0, 8)
    }

    private fun render() {
        list.removeAllViews()
        list.addView(heading("Current sensor sessions"))
        val sessions = SensoriumSessionRegistry.active()
        if (sessions.isEmpty()) {
            list.addView(TextView(this).apply {
                text = "Camera OFF · Microphone OFF · Screen OFF · Location OFF · Motion OFF · Environment OFF · Network OFF · Clipboard OFF · Wearable OFF · Spatial OFF"
                textSize = 16f
            })
        } else {
            sessions.forEach { grant ->
                val remaining = ((grant.expiresAtMs - System.currentTimeMillis()).coerceAtLeast(0) / 1000)
                val requester = grant.requestedByDeviceId ?: "local owner"
                list.addView(TextView(this).apply {
                    text = "${grant.sensor.uppercase()} · SESSION · ${remaining}s remaining · ${grant.resourceId}\nRequested by: $requester\nReason: ${grant.reason}\nAuthority: explicit local owner consent on this device"
                    textSize = 15f
                    setPadding(0, 12, 0, 12)
                })
            }
        }
        list.addView(TextView(this).apply {
            val screen = SensoriumScreenBridge.active()
            val spatial = SensoriumSpatialBridge.status().optBoolean("active")
            val camera = VisionCameraBridge.status(this@SensoriumPrivacyActivity).optBoolean("active")
            text = "Hardware: Camera ${if(camera)"ON" else "OFF"} · Screen ${if(screen)"ON" else "OFF"} · Spatial ${if(spatial)"ON" else "OFF"}"
            textSize = 14f
        })

        list.addView(heading("Retention"))
        list.addView(TextView(this).apply {
            text = "Raw camera/screen frames: not retained by Sensorium. Continuous environmental audio: not retained. Clipboard reads: not retained. Wearable relay observations: semantic-only. Exact mobile location: not written to the semantic World Model by default. Semantic summaries follow the selected memory mode. Selected media is saved only when explicitly chosen and privacy-processed."
            textSize = 14f
        })

        list.addView(heading("Recent local sensor audit"))
        val audit = SensoriumSessionRegistry.recentAudit(12)
        if (audit.isEmpty()) {
            list.addView(TextView(this).apply { text = "No local Sensorium session events yet."; textSize = 14f })
        } else {
            val formatter = DateFormat.getTimeInstance(DateFormat.MEDIUM)
            audit.forEach { row ->
                val requester = row.requestedByDeviceId ?: "local owner"
                list.addView(TextView(this).apply {
                    text = "${formatter.format(Date(row.createdAtMs))} · ${row.action} · ${row.sensor.uppercase()} · ${row.resourceId}\nRequested by: $requester\n${row.reason}"
                    textSize = 13f
                    setPadding(0, 7, 0, 7)
                })
            }
        }
        list.addView(TextView(this).apply {
            text = "The Vishnu server also keeps the persistent per-device sensor permission audit, including requesting-device provenance; this list is the current app-process audit."
            textSize = 12f
        })
    }

    private fun stopAll() {
        VisionCameraBridge.deactivate()
        SensoriumScreenBridge.stop()
        SensoriumSpatialBridge.stop()
        SensoriumWearableRelay.clear()
        stopService(Intent(this, SensoriumScreenCaptureService::class.java))
        stopService(Intent(this, SensoriumAudioService::class.java))
        SensoriumSessionRegistry.stopAll()
    }
}
