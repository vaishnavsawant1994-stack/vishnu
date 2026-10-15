package ai.personal.companion

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class SensoriumPrivacyActivity : AppCompatActivity() {
    private lateinit var list: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(28, 32, 28, 32) }
        root.addView(TextView(this).apply { text = "Sensorium Privacy"; textSize = 24f })
        root.addView(TextView(this).apply {
            text = "Every sensor is session-only. This screen shows local active grants. Seeing/hearing never grants Computer Control, Device Control or tool authority."
            textSize = 14f
        })
        val refresh = Button(this).apply { text = "Refresh sensor status"; setOnClickListener { render() } }
        val stop = Button(this).apply { text = "STOP ALL SENSING"; setOnClickListener { stopAll(); render() } }
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(refresh); root.addView(stop); root.addView(list)
        setContentView(ScrollView(this).apply { addView(root) })
        render()
    }

    private fun render() {
        list.removeAllViews()
        val sessions = SensoriumSessionRegistry.active()
        if (sessions.isEmpty()) {
            list.addView(TextView(this).apply { text = "Camera OFF · Microphone OFF · Screen OFF · Location OFF · Motion OFF · Spatial OFF"; textSize = 16f })
        } else {
            sessions.forEach { grant ->
                val remaining = ((grant.expiresAtMs - System.currentTimeMillis()).coerceAtLeast(0) / 1000)
                list.addView(TextView(this).apply {
                    text = "${grant.sensor.uppercase()} · SESSION · ${remaining}s remaining · ${grant.resourceId}\nReason: ${grant.reason}"
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
    }

    private fun stopAll() {
        VisionCameraBridge.deactivate()
        SensoriumScreenBridge.stop()
        SensoriumSpatialBridge.stop()
        stopService(Intent(this, SensoriumScreenCaptureService::class.java))
        stopService(Intent(this, SensoriumAudioService::class.java))
        SensoriumSessionRegistry.stopAll()
    }
}
