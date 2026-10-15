package ai.personal.companion

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.media.FaceDetector
import android.os.BatteryManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.time.Instant
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.max
import kotlin.math.min

object VisionCameraBridge {
    const val MIN_LIVE_BATTERY_PERCENT = 15
    private val lock = Any()
    @Volatile private var imageCapture: ImageCapture? = null
    @Volatile private var activeFacing: String = "front"
    @Volatile private var activeCameraId: String = "mobile:front"
    @Volatile private var sensorSessionId: String? = null
    @Volatile private var expiresAtMs: Long = 0
    @Volatile private var closeOwner: (() -> Unit)? = null

    fun cameras(context: Context): JSONObject {
        val manager = context.getSystemService(CameraManager::class.java)
        val rows = JSONArray()
        manager.cameraIdList.take(32).forEach { id ->
            val chars = manager.getCameraCharacteristics(id)
            val lens = chars.get(CameraCharacteristics.LENS_FACING)
            val facing = when(lens) {
                CameraCharacteristics.LENS_FACING_FRONT -> "front"
                CameraCharacteristics.LENS_FACING_BACK -> "back"
                CameraCharacteristics.LENS_FACING_EXTERNAL -> "external"
                else -> "unknown"
            }
            rows.put(JSONObject()
                .put("camera_id", "mobile:$id")
                .put("label", "${facing.replaceFirstChar { it.uppercase() }} camera ($id)")
                .put("facing", facing)
                .put("external", lens == CameraCharacteristics.LENS_FACING_EXTERNAL))
        }
        return JSONObject().put("cameras", rows)
    }

    fun activate(capture: ImageCapture, facing: String, cameraId: String, ttlMs: Long = 5 * 60_000L, onClose: () -> Unit) {
        synchronized(lock) {
            imageCapture = capture
            activeFacing = facing
            activeCameraId = cameraId
            sensorSessionId = UUID.randomUUID().toString()
            expiresAtMs = System.currentTimeMillis() + ttlMs
            closeOwner = onClose
        }
    }

    fun deactivate(closeCameraOwner: Boolean = true) {
        val closer = synchronized(lock) {
            val action = if (closeCameraOwner) closeOwner else null
            imageCapture = null
            expiresAtMs = 0
            sensorSessionId = null
            closeOwner = null
            action
        }
        if (closer != null) Handler(Looper.getMainLooper()).post { closer.invoke() }
    }

    fun remainingSeconds(): Long = max(0L, (expiresAtMs - System.currentTimeMillis() + 999L) / 1000L)

    private fun batteryPercent(context: Context): Int {
        val manager = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        return manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
    }

    fun status(context: Context): JSONObject {
        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        val active = imageCapture != null && System.currentTimeMillis() < expiresAtMs
        if (!active && imageCapture != null) deactivate()
        return JSONObject()
            .put("active", active)
            .put("permission", if (granted) "granted" else "not_granted")
            .put("foreground_required", true)
            .put("facing", activeFacing)
            .put("camera_id", activeCameraId)
            .put("sensor_session_id", if (active) sensorSessionId else JSONObject.NULL)
            .put("expires_at", if (active) Instant.ofEpochMilli(expiresAtMs).toString() else JSONObject.NULL)
            .put("remaining_seconds", if (active) remainingSeconds() else 0)
            .put("battery_percent", batteryPercent(context))
            .put("min_live_battery_percent", MIN_LIVE_BATTERY_PERCENT)
    }

    private fun normalizedRect(obj: JSONObject, width: Int, height: Int): android.graphics.Rect {
        val x = obj.optDouble("x", 0.0).coerceIn(0.0, 1.0)
        val y = obj.optDouble("y", 0.0).coerceIn(0.0, 1.0)
        val w = obj.optDouble("width", 0.0).coerceIn(0.0, 1.0)
        val h = obj.optDouble("height", 0.0).coerceIn(0.0, 1.0)
        require(w > 0 && h > 0 && x + w <= 1.000001 && y + h <= 1.000001) { "Invalid privacy region" }
        val left = (x * width).toInt().coerceIn(0, max(0, width - 1))
        val top = (y * height).toInt().coerceIn(0, max(0, height - 1))
        val right = ((x + w) * width).toInt().coerceIn(left + 1, width)
        val bottom = ((y + h) * height).toInt().coerceIn(top + 1, height)
        return android.graphics.Rect(left, top, right, bottom)
    }

    private fun pixelate(bitmap: Bitmap, rect: android.graphics.Rect) {
        val safe = android.graphics.Rect(
            rect.left.coerceIn(0, bitmap.width - 1), rect.top.coerceIn(0, bitmap.height - 1),
            rect.right.coerceIn(1, bitmap.width), rect.bottom.coerceIn(1, bitmap.height)
        )
        if (safe.width() <= 1 || safe.height() <= 1) return
        val region = Bitmap.createBitmap(bitmap, safe.left, safe.top, safe.width(), safe.height())
        val tiny = Bitmap.createScaledBitmap(region, max(1, safe.width() / 20), max(1, safe.height() / 20), false)
        val obscured = Bitmap.createScaledBitmap(tiny, safe.width(), safe.height(), false)
        Canvas(bitmap).drawBitmap(obscured, safe.left.toFloat(), safe.top.toFloat(), Paint(Paint.ANTI_ALIAS_FLAG))
        region.recycle(); tiny.recycle(); obscured.recycle()
    }

    private fun redactFaces(bitmap: Bitmap): Int {
        val evenWidth = if (bitmap.width % 2 == 0) bitmap.width else bitmap.width - 1
        if (evenWidth < 2 || bitmap.height < 2) return 0
        val source = Bitmap.createBitmap(bitmap, 0, 0, evenWidth, bitmap.height)
            .copy(Bitmap.Config.RGB_565, false)
        val faces = arrayOfNulls<FaceDetector.Face>(16)
        val detector = FaceDetector(source.width, source.height, faces.size)
        val count = detector.findFaces(source, faces)
        faces.take(count).filterNotNull().forEach { face ->
            val point = android.graphics.PointF(); face.getMidPoint(point)
            val span = max(32f, face.eyesDistance() * 3.6f)
            val rect = android.graphics.Rect(
                max(0, (point.x - span / 2).toInt()),
                max(0, (point.y - span * 0.55f).toInt()),
                min(bitmap.width, (point.x + span / 2).toInt()),
                min(bitmap.height, (point.y + span * 0.65f).toInt())
            )
            if (rect.width() > 1 && rect.height() > 1) pixelate(bitmap, rect)
        }
        source.recycle()
        return count
    }

    private fun privacyProcess(bytes: ByteArray, privacy: JSONObject): Pair<ByteArray, JSONObject> {
        var bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.copy(Bitmap.Config.ARGB_8888, true)
            ?: throw IllegalStateException("Camera snapshot could not be decoded")
        val originalWidth = bitmap.width; val originalHeight = bitmap.height
        privacy.optJSONObject("crop")?.let { crop ->
            val rect = normalizedRect(crop, bitmap.width, bitmap.height)
            val cropped = Bitmap.createBitmap(bitmap, rect.left, rect.top, rect.width(), rect.height())
            bitmap.recycle(); bitmap = cropped.copy(Bitmap.Config.ARGB_8888, true); cropped.recycle()
        }
        val regions = privacy.optJSONArray("redact_regions") ?: JSONArray()
        for (i in 0 until min(regions.length(), 64)) {
            regions.optJSONObject(i)?.let { pixelate(bitmap, normalizedRect(it, bitmap.width, bitmap.height)) }
        }
        val requireFaces = privacy.optBoolean("require_face_redaction", false)
        val faceCount = if (requireFaces) redactFaces(bitmap) else 0
        val maxEdge = privacy.optInt("max_edge", 1024).coerceIn(64, 1280)
        if (max(bitmap.width, bitmap.height) > maxEdge) {
            val scale = maxEdge.toFloat() / max(bitmap.width, bitmap.height).toFloat()
            val resized = Bitmap.createScaledBitmap(bitmap, max(1, (bitmap.width * scale).toInt()), max(1, (bitmap.height * scale).toInt()), true)
            bitmap.recycle(); bitmap = resized
        }
        val out = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, 68, out)
        val processed = out.toByteArray()
        val meta = JSONObject()
            .put("original_width", originalWidth).put("original_height", originalHeight)
            .put("width", bitmap.width).put("height", bitmap.height)
            .put("redacted_regions", regions.length().coerceAtMost(64))
            .put("faces_processed", requireFaces)
            .put("faces_detected", faceCount)
            .put("privacy_processed", true)
        bitmap.recycle()
        require(processed.isNotEmpty() && processed.size <= 1_500_000) { "Privacy-processed snapshot is empty or too large" }
        return Pair(processed, meta)
    }

    fun snapshot(context: Context, privacy: JSONObject = JSONObject()): JSONObject {
        val capture = imageCapture ?: throw IllegalStateException("Open the Vishnu Vision notification and enable the camera first")
        val session = sensorSessionId ?: throw IllegalStateException("Vishnu Vision sensor session is unavailable")
        if (System.currentTimeMillis() >= expiresAtMs) {
            deactivate()
            throw IllegalStateException("Vishnu Vision session expired")
        }
        val battery = batteryPercent(context)
        if (battery in 0 until MIN_LIVE_BATTERY_PERCENT) {
            deactivate()
            throw IllegalStateException("Vishnu Vision stopped because battery is below ${MIN_LIVE_BATTERY_PERCENT}%")
        }
        val file = File.createTempFile("vishnu-vision-", ".jpg", context.cacheDir)
        val error = AtomicReference<Throwable?>(null)
        val latch = CountDownLatch(1)
        try {
            val output = ImageCapture.OutputFileOptions.Builder(file).build()
            capture.takePicture(output, ContextCompat.getMainExecutor(context), object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) { latch.countDown() }
                override fun onError(exception: ImageCaptureException) { error.set(exception); latch.countDown() }
            })
            if (!latch.await(10, TimeUnit.SECONDS)) throw IllegalStateException("Camera snapshot timed out")
            error.get()?.let { throw IllegalStateException("Camera snapshot failed") }
            val bytes = file.readBytes()
            require(bytes.isNotEmpty() && bytes.size <= 4_000_000) { "Camera snapshot is empty or too large" }
            val (processed, privacyMeta) = privacyProcess(bytes, privacy)
            return JSONObject()
                .put("mime_type", "image/jpeg")
                .put("base64", Base64.encodeToString(processed, Base64.NO_WRAP))
                .put("width", privacyMeta.getInt("width"))
                .put("height", privacyMeta.getInt("height"))
                .put("facing", activeFacing)
                .put("camera_id", activeCameraId)
                .put("sensor_session_id", session)
                .put("privacy", privacyMeta)
                .put("battery_percent", battery)
                .put("min_live_battery_percent", MIN_LIVE_BATTERY_PERCENT)
                .put("captured_at", Instant.now().toString())
        } finally {
            file.delete()
        }
    }
}

class VisionCameraActivity : AppCompatActivity() {
    companion object { private const val CAMERA_REQUEST = 4201 }
    private lateinit var previewView: PreviewView
    private lateinit var status: TextView
    private var provider: ProcessCameraProvider? = null
    private var selectedCameraLabel: String = "camera"
    private val timerHandler = Handler(Looper.getMainLooper())
    private val timerTick = object : Runnable {
        override fun run() {
            if (isFinishing) return
            val remaining = VisionCameraBridge.remainingSeconds()
            if (remaining <= 0) { finish(); return }
            status.text = "Vishnu Vision active · $selectedCameraLabel · ${remaining}s remaining · battery floor ${VisionCameraBridge.MIN_LIVE_BATTERY_PERCENT}% · bounded data/model sampling"
            timerHandler.postDelayed(this, 1000L)
        }
    }
    private val requestedFacing: String by lazy {
        when (intent?.getStringExtra("facing")?.lowercase()) { "back" -> "back"; else -> "front" }
    }
    private val requestedCameraId: String by lazy { intent?.getStringExtra("camera_id")?.trim().orEmpty() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 32, 24, 32) }
        status = TextView(this).apply {
            text = "Vishnu Vision needs your camera permission. The camera stops when you leave this screen or after 5 minutes."
            textSize = 16f
        }
        previewView = PreviewView(this).apply { layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f) }
        val stop = Button(this).apply { text = "Stop Vishnu Vision"; setOnClickListener { finish() } }
        root.addView(status); root.addView(previewView); root.addView(stop); setContentView(root)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) bindCamera()
        else ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), CAMERA_REQUEST)
        Handler(Looper.getMainLooper()).postDelayed({ if (!isFinishing) finish() }, 5 * 60_000L)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == CAMERA_REQUEST && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) bindCamera()
        else { status.text = "Camera permission was not granted."; VisionCameraBridge.deactivate() }
    }

    private fun selector(): Pair<CameraSelector, String> {
        if (requestedCameraId.startsWith("mobile:") && requestedCameraId !in setOf("mobile:front", "mobile:back", "mobile:auto")) {
            val hardwareId = requestedCameraId.removePrefix("mobile:")
            val selector = CameraSelector.Builder().addCameraFilter { infos ->
                infos.filter { info -> runCatching { Camera2CameraInfo.from(info).cameraId == hardwareId }.getOrDefault(false) }
            }.build()
            return Pair(selector, requestedCameraId)
        }
        val selector = if (requestedFacing == "back" || requestedCameraId == "mobile:back") CameraSelector.DEFAULT_BACK_CAMERA else CameraSelector.DEFAULT_FRONT_CAMERA
        val id = if (requestedFacing == "back" || requestedCameraId == "mobile:back") "mobile:back" else "mobile:front"
        return Pair(selector, id)
    }

    private fun bindCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            try {
                val cameraProvider = future.get(); provider = cameraProvider
                val preview = Preview.Builder().build().also { it.setSurfaceProvider(previewView.surfaceProvider) }
                val capture = ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).setJpegQuality(75).build()
                val selected = selector(); selectedCameraLabel = selected.second
                cameraProvider.unbindAll(); cameraProvider.bindToLifecycle(this, selected.first, preview, capture)
                VisionCameraBridge.activate(capture, requestedFacing, selected.second) {
                    provider?.unbindAll(); if (!isFinishing) finish()
                }
                timerHandler.removeCallbacks(timerTick); timerHandler.post(timerTick)
            } catch (_: Exception) {
                VisionCameraBridge.deactivate(); status.text = "Camera is unavailable on this device."
            }
        }, ContextCompat.getMainExecutor(this))
    }

    override fun onStop() {
        timerHandler.removeCallbacks(timerTick)
        VisionCameraBridge.deactivate(closeCameraOwner = false); provider?.unbindAll(); super.onStop()
    }
    override fun onDestroy() {
        timerHandler.removeCallbacks(timerTick)
        VisionCameraBridge.deactivate(closeCameraOwner = false); provider?.unbindAll(); super.onDestroy()
    }
}
