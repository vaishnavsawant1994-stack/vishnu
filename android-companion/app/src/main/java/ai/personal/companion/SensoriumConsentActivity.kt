package ai.personal.companion

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class SensoriumConsentActivity : AppCompatActivity() {
    companion object { private const val REQUEST = 7301 }

    private lateinit var status: TextView
    private val sensor by lazy { intent?.getStringExtra("sensor")?.trim()?.lowercase().orEmpty() }
    private val resource by lazy { intent?.getStringExtra("resource_id")?.trim().orEmpty().ifBlank { "*" } }
    private val reason by lazy { intent?.getStringExtra("reason")?.trim().orEmpty().ifBlank { "Vishnu requested temporary context." } }
    private val requester by lazy { intent?.getStringExtra("requesting_device_id")?.trim()?.take(200).orEmpty() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(32, 40, 32, 40) }
        val requesterText = if (requester.isBlank()) "Requested locally on this device" else "Requested by trusted device: $requester"
        status = TextView(this).apply {
            text = "Vishnu wants temporary access to $sensor.\n\n$requesterText\n\n$reason\n\nThis session expires automatically. It does not grant Computer Control, Device Control or tool authority."
            textSize = 17f
        }
        val allow = Button(this).apply { text = "Allow this session"; setOnClickListener { approve() } }
        val deny = Button(this).apply { text = "Not now"; setOnClickListener { finish() } }
        root.addView(status); root.addView(allow); root.addView(deny); setContentView(root)
        Handler(Looper.getMainLooper()).postDelayed({ if (!isFinishing) finish() }, 2 * 60_000L)
    }

    private fun requiredPermissions(): Array<String> = when (sensor) {
        "location" -> arrayOf(Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION)
        "microphone", "audio" -> arrayOf(Manifest.permission.RECORD_AUDIO)
        "motion" -> if (android.os.Build.VERSION.SDK_INT >= 29) arrayOf(Manifest.permission.ACTIVITY_RECOGNITION) else emptyArray()
        "document", "spatial" -> arrayOf(Manifest.permission.CAMERA)
        else -> emptyArray()
    }

    private fun approve() {
        if (sensor !in setOf("location", "motion", "environment", "network", "microphone", "audio", "screen", "document", "spatial", "wearable", "iot", "clipboard")) {
            status.text = "Unsupported Sensorium sensor."
            return
        }
        if (sensor == "screen") {
            startActivity(Intent(this, SensoriumScreenActivity::class.java)
                .putExtra("reason", reason)
                .putExtra("requesting_device_id", requester))
            finish(); return
        }
        val missing = requiredPermissions().filter { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), REQUEST)
            return
        }
        grantAndFinish()
    }

    private fun grantAndFinish() {
        val kind = if (sensor == "audio") "microphone" else sensor
        SensoriumSessionRegistry.grant(kind, resource, reason = reason, requestedByDeviceId = requester.ifBlank { null })
        when (kind) {
            "spatial" -> {
                SensoriumSessionRegistry.revoke("spatial", resource)
                startActivity(Intent(this, SensoriumSpatialActivity::class.java)
                    .putExtra("reason", reason)
                    .putExtra("requesting_device_id", requester))
                finish()
            }
            "document" -> {
                startActivity(Intent(this, VisionCameraActivity::class.java).putExtra("facing", "back").putExtra("camera_id", "mobile:back"))
                finish()
            }
            "microphone" -> {
                ContextCompat.startForegroundService(this, Intent(this, SensoriumAudioService::class.java))
                status.text = "Microphone allowed for this session. Android will keep a visible Vishnu audio notification."
                Handler(Looper.getMainLooper()).postDelayed({ finish() }, 900)
            }
            else -> {
                status.text = "$kind allowed for this session. Expires automatically."
                Handler(Looper.getMainLooper()).postDelayed({ finish() }, 700)
            }
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST) return
        if (grantResults.isNotEmpty() && grantResults.any { it == PackageManager.PERMISSION_GRANTED }) grantAndFinish()
        else status.text = "OS permission was not granted. Vishnu cannot use $sensor."
    }
}
