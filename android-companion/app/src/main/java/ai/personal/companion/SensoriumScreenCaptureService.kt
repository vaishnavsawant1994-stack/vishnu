package ai.personal.companion

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.hardware.display.DisplayManager
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.util.Base64
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import java.time.Instant
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.max

object SensoriumScreenBridge {
    @Volatile private var reader: ImageReader? = null
    @Volatile private var projection: MediaProjection? = null
    @Volatile private var width: Int = 0
    @Volatile private var height: Int = 0
    @Volatile private var previousFingerprint: String? = null

    fun attach(mediaProjection: MediaProjection, imageReader: ImageReader, w: Int, h: Int) {
        projection = mediaProjection; reader = imageReader; width = w; height = h; previousFingerprint = null
    }

    fun stop() {
        runCatching { projection?.stop() }
        runCatching { reader?.close() }
        projection = null; reader = null; width = 0; height = 0; previousFingerprint = null
        SensoriumSessionRegistry.revoke("screen", "mobile:screen")
    }

    fun active(): Boolean = projection != null && reader != null && SensoriumSessionRegistry.get("screen", "mobile:screen") != null

    private fun latestBitmap(): Bitmap {
        val image = reader?.acquireLatestImage() ?: throw IllegalStateException("No current screen frame is available yet")
        try {
            val plane = image.planes.first()
            val pixelStride = plane.pixelStride
            val rowStride = plane.rowStride
            val rowPadding = rowStride - pixelStride * image.width
            val paddedWidth = image.width + rowPadding / pixelStride
            val bitmap = Bitmap.createBitmap(paddedWidth, image.height, Bitmap.Config.ARGB_8888)
            bitmap.copyPixelsFromBuffer(plane.buffer)
            val cropped = Bitmap.createBitmap(bitmap, 0, 0, image.width, image.height)
            if (cropped !== bitmap) bitmap.recycle()
            return cropped
        } finally { image.close() }
    }

    private fun sanitize(source: Bitmap): Bitmap {
        var bitmap = source
        val maxEdge = 1024
        if (max(bitmap.width, bitmap.height) > maxEdge) {
            val scale = maxEdge.toFloat() / max(bitmap.width, bitmap.height).toFloat()
            val resized = Bitmap.createScaledBitmap(bitmap, max(1, (bitmap.width * scale).toInt()), max(1, (bitmap.height * scale).toInt()), true)
            if (resized !== bitmap) bitmap.recycle(); bitmap = resized
        }
        val copy = bitmap.copy(Bitmap.Config.ARGB_8888, true)
        if (copy !== bitmap) bitmap.recycle()
        val canvas = Canvas(copy)
        val paint = Paint().apply { color = Color.BLACK }
        // System status/navigation areas frequently expose notifications, carrier,
        // other-app state, or transient private information. Redact them locally.
        canvas.drawRect(0f, 0f, copy.width.toFloat(), copy.height * 0.07f, paint)
        canvas.drawRect(0f, copy.height * 0.94f, copy.width.toFloat(), copy.height.toFloat(), paint)
        return copy
    }

    private fun fingerprint(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).take(12).joinToString("") { "%02x".format(it) }

    private fun localText(bitmap: Bitmap): String {
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        val result = AtomicReference<String>("")
        val latch = CountDownLatch(1)
        recognizer.process(InputImage.fromBitmap(bitmap, 0))
            .addOnSuccessListener { result.set(it.text.take(20_000)); latch.countDown() }
            .addOnFailureListener { latch.countDown() }
        latch.await(4, TimeUnit.SECONDS)
        recognizer.close()
        return result.get()
    }

    fun snapshot(): JSONObject {
        val grant = SensoriumSessionRegistry.require("screen", "mobile:screen")
        val bitmap = sanitize(latestBitmap())
        try {
            val text = localText(bitmap)
            val out = ByteArrayOutputStream()
            bitmap.compress(Bitmap.CompressFormat.JPEG, 68, out)
            val bytes = out.toByteArray()
            require(bytes.isNotEmpty() && bytes.size <= 1_500_000) { "Privacy-processed screen snapshot is too large" }
            val current = fingerprint(bytes)
            val changed = previousFingerprint == null || previousFingerprint != current
            previousFingerprint = current
            return JSONObject()
                .put("mime_type", "image/jpeg")
                .put("base64", Base64.encodeToString(bytes, Base64.NO_WRAP))
                .put("width", bitmap.width).put("height", bitmap.height)
                .put("local_text", text)
                .put("screen_fingerprint", current)
                .put("scene_changed", changed)
                .put("privacy_processed", true)
                .put("raw_frame_retained", false)
                .put("resource_id", "mobile:screen")
                .put("sensor_session_id", grant.sessionId)
                .put("expires_at_epoch", grant.expiresAtMs / 1000.0)
                .put("local_consent", true)
                .put("captured_at", Instant.now().toEpochMilli() / 1000.0)
        } finally { bitmap.recycle() }
    }
}

class SensoriumScreenCaptureService : Service() {
    companion object { private const val CHANNEL = "vishnu_sensorium_screen"; private const val NOTIFICATION = 94 }
    private var projection: MediaProjection? = null
    private var reader: ImageReader? = null
    private var display: android.hardware.display.VirtualDisplay? = null

    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, "Vishnu Screen Understanding", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Visible while Vishnu has a temporary owner-approved screen session"
            }
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_view)
            .setContentTitle("Vishnu can see this screen")
            .setContentText("Temporary owner-approved Sensorium screen session")
            .setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(NOTIFICATION, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        else startForeground(NOTIFICATION, notification)
        val code = intent?.getIntExtra("result_code", Activity.RESULT_CANCELED) ?: Activity.RESULT_CANCELED
        @Suppress("DEPRECATION")
        val data = if (Build.VERSION.SDK_INT >= 33) intent?.getParcelableExtra("result_data", Intent::class.java) else intent?.getParcelableExtra("result_data") as? Intent
        if (code != Activity.RESULT_OK || data == null) { stopSelf(); return START_NOT_STICKY }
        val manager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val mediaProjection = manager.getMediaProjection(code, data)
        projection = mediaProjection
        val metrics = resources.displayMetrics
        val w = metrics.widthPixels.coerceAtLeast(1); val h = metrics.heightPixels.coerceAtLeast(1)
        val imageReader = ImageReader.newInstance(w, h, android.graphics.PixelFormat.RGBA_8888, 2)
        reader = imageReader
        display = mediaProjection.createVirtualDisplay(
            "VishnuSensoriumScreen", w, h, metrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader.surface, null, null
        )
        val reason = intent.getStringExtra("reason") ?: "Owner approved mobile screen understanding"
        SensoriumSessionRegistry.grant("screen", "mobile:screen", reason = reason)
        SensoriumScreenBridge.attach(mediaProjection, imageReader, w, h)
        mediaProjection.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() { shutdown() }
        }, android.os.Handler(mainLooper))
        return START_NOT_STICKY
    }

    private fun shutdown() {
        runCatching { display?.release() }; display = null
        SensoriumScreenBridge.stop(); projection = null; reader = null
        stopForeground(STOP_FOREGROUND_REMOVE); stopSelf()
    }

    override fun onDestroy() { shutdown(); super.onDestroy() }
    override fun onBind(intent: Intent?): IBinder? = null
}
