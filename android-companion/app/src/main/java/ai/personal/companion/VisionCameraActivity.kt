package ai.personal.companion

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

object VisionCameraBridge {
    private val lock = Any()
    @Volatile private var imageCapture: ImageCapture? = null
    @Volatile private var activeFacing: String = "front"
    @Volatile private var expiresAtMs: Long = 0
    @Volatile private var closeOwner: (() -> Unit)? = null

    fun activate(capture: ImageCapture, facing: String, ttlMs: Long = 5 * 60_000L, onClose: () -> Unit) {
        synchronized(lock) {
            imageCapture = capture
            activeFacing = facing
            expiresAtMs = System.currentTimeMillis() + ttlMs
            closeOwner = onClose
        }
    }

    fun deactivate(closeCameraOwner: Boolean = true) {
        val closer = synchronized(lock) {
            val action = if (closeCameraOwner) closeOwner else null
            imageCapture = null
            expiresAtMs = 0
            closeOwner = null
            action
        }
        if (closer != null) Handler(Looper.getMainLooper()).post { closer.invoke() }
    }

    fun status(context: android.content.Context): JSONObject {
        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        val active = imageCapture != null && System.currentTimeMillis() < expiresAtMs
        if (!active && imageCapture != null) deactivate()
        return JSONObject()
            .put("active", active)
            .put("permission", if (granted) "granted" else "not_granted")
            .put("foreground_required", true)
            .put("facing", activeFacing)
            .put("expires_at", if (active) Instant.ofEpochMilli(expiresAtMs).toString() else JSONObject.NULL)
    }

    fun snapshot(context: android.content.Context): JSONObject {
        val capture = imageCapture ?: throw IllegalStateException("Open the Vishnu Vision notification and enable the camera first")
        if (System.currentTimeMillis() >= expiresAtMs) {
            deactivate()
            throw IllegalStateException("Vishnu Vision session expired")
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
            require(bytes.isNotEmpty() && bytes.size <= 1_500_000) { "Camera snapshot is empty or too large" }
            val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
            return JSONObject()
                .put("mime_type", "image/jpeg")
                .put("base64", Base64.encodeToString(bytes, Base64.NO_WRAP))
                .put("width", options.outWidth)
                .put("height", options.outHeight)
                .put("facing", activeFacing)
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
    private val requestedFacing: String by lazy {
        when (intent?.getStringExtra("facing")?.lowercase()) { "back" -> "back"; else -> "front" }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 32, 24, 32)
        }
        status = TextView(this).apply {
            text = "Vishnu Vision needs your camera permission. The camera stops when you leave this screen or after 5 minutes."
            textSize = 16f
        }
        previewView = PreviewView(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
        }
        val stop = Button(this).apply {
            text = "Stop Vishnu Vision"
            setOnClickListener { finish() }
        }
        root.addView(status)
        root.addView(previewView)
        root.addView(stop)
        setContentView(root)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            bindCamera()
        } else {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), CAMERA_REQUEST)
        }
        Handler(Looper.getMainLooper()).postDelayed({ if (!isFinishing) finish() }, 5 * 60_000L)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == CAMERA_REQUEST && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) bindCamera()
        else { status.text = "Camera permission was not granted."; VisionCameraBridge.deactivate() }
    }

    private fun bindCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            try {
                val cameraProvider = future.get()
                provider = cameraProvider
                val preview = Preview.Builder().build().also { it.setSurfaceProvider(previewView.surfaceProvider) }
                val capture = ImageCapture.Builder()
                    .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                    .setJpegQuality(75)
                    .build()
                val selector = if (requestedFacing == "back") CameraSelector.DEFAULT_BACK_CAMERA else CameraSelector.DEFAULT_FRONT_CAMERA
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(this, selector, preview, capture)
                VisionCameraBridge.activate(capture, requestedFacing) {
                    provider?.unbindAll()
                    if (!isFinishing) finish()
                }
                status.text = "Vishnu Vision is active · snapshot-only · raw frames are not retained · stops automatically."
            } catch (_: Exception) {
                VisionCameraBridge.deactivate()
                status.text = "Camera is unavailable on this device."
            }
        }, ContextCompat.getMainExecutor(this))
    }

    override fun onStop() {
        VisionCameraBridge.deactivate(closeCameraOwner = false)
        provider?.unbindAll()
        super.onStop()
    }

    override fun onDestroy() {
        VisionCameraBridge.deactivate(closeCameraOwner = false)
        provider?.unbindAll()
        super.onDestroy()
    }
}
