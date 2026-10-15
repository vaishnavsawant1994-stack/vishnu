package ai.personal.companion

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

class SensoriumScreenActivity : AppCompatActivity() {
    private lateinit var status: TextView
    private val launcher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode != Activity.RESULT_OK || result.data == null) {
            status.text = "Screen sharing was not approved."
            return@registerForActivityResult
        }
        val reason = intent?.getStringExtra("reason") ?: "Vishnu requested temporary screen understanding."
        val service = Intent(this, SensoriumScreenCaptureService::class.java)
            .putExtra("result_code", result.resultCode)
            .putExtra("result_data", result.data)
            .putExtra("reason", reason)
        ContextCompat.startForegroundService(this, service)
        status.text = "Vishnu Screen session started. Android will keep a visible screen-sharing indicator."
        window.decorView.postDelayed({ finish() }, 900)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(32, 40, 32, 40) }
        status = TextView(this).apply {
            text = "Android will show its system screen-sharing confirmation next. Vishnu only keeps privacy-processed snapshots for the active session, never a silent permanent capture."
            textSize = 17f
        }
        root.addView(status); setContentView(root)
        val manager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        launcher.launch(manager.createScreenCaptureIntent())
    }
}
