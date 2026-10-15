package ai.personal.companion

import android.Manifest
import android.content.pm.PackageManager
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.google.ar.core.Config
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.util.concurrent.atomic.AtomicReference
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

object SensoriumSpatialBridge {
    private val latest = AtomicReference<JSONObject?>(null)
    @Volatile private var active = false

    fun update(value: JSONObject) { latest.set(value); active = true }
    fun stop() { latest.set(null); active = false; SensoriumSessionRegistry.revoke("spatial", "mobile:spatial") }
    fun status(): JSONObject = JSONObject().put("active", active).put("available", latest.get() != null)
    fun snapshot(): JSONObject {
        val grant = SensoriumSessionRegistry.require("spatial", "mobile:spatial")
        val value = latest.get() ?: throw IllegalStateException("Open Vishnu Spatial View and move the phone so ARCore can map the room")
        return JSONObject(value.toString())
            .put("resource_id", grant.resourceId)
            .put("sensor_session_id", grant.sessionId)
            .put("expires_at_epoch", grant.expiresAtMs / 1000.0)
            .put("local_consent", true)
            .put("captured_at", Instant.now().toEpochMilli() / 1000.0)
            .put("execution_authority", false)
    }
}

class SensoriumSpatialActivity : AppCompatActivity(), GLSurfaceView.Renderer {
    companion object { private const val CAMERA_REQUEST = 7401 }
    private lateinit var surface: GLSurfaceView
    private lateinit var status: TextView
    private var session: Session? = null
    private var textureId = 0
    private var depthAvailable = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 28, 20, 28) }
        status = TextView(this).apply {
            text = "Vishnu Spatial View maps local 3D geometry only while this screen is open. Move the phone slowly."
            textSize = 16f
        }
        surface = GLSurfaceView(this).apply {
            setEGLContextClientVersion(2)
            setRenderer(this@SensoriumSpatialActivity)
            renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
        }
        root.addView(status)
        root.addView(surface, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), CAMERA_REQUEST)
        } else startSession()
    }

    private fun startSession() {
        try {
            val ar = Session(this)
            val config = Config(ar)
            depthAvailable = ar.isDepthModeSupported(Config.DepthMode.AUTOMATIC)
            if (depthAvailable) config.depthMode = Config.DepthMode.AUTOMATIC
            config.updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
            ar.configure(config)
            session = ar
            SensoriumSessionRegistry.grant("spatial", "mobile:spatial", reason = "Owner opened Vishnu Spatial View")
            status.text = if (depthAvailable) "Spatial View active · ARCore depth available · local geometry only" else "Spatial View active · ARCore tracking · depth sensor unavailable"
        } catch (exc: Exception) {
            status.text = "ARCore spatial sensing is unavailable: ${exc.message ?: exc.javaClass.simpleName}"
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == CAMERA_REQUEST && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) startSession()
        else status.text = "Camera permission is required for ARCore spatial sensing."
    }

    override fun onResume() {
        super.onResume(); surface.onResume()
        try { session?.resume() } catch (_: Exception) { }
    }

    override fun onPause() {
        runCatching { session?.pause() }; surface.onPause(); super.onPause()
    }

    override fun onDestroy() {
        runCatching { session?.close() }; session = null; SensoriumSpatialBridge.stop(); super.onDestroy()
    }

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        val ids = IntArray(1)
        GLES20.glGenTextures(1, ids, 0); textureId = ids[0]
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textureId)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        session?.setCameraTextureName(textureId)
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) { GLES20.glViewport(0, 0, width, height) }

    override fun onDrawFrame(gl: GL10?) {
        val ar = session ?: return
        try {
            if (textureId != 0) ar.setCameraTextureName(textureId)
            val frame = ar.update()
            val camera = frame.camera
            if (camera.trackingState != TrackingState.TRACKING) return
            val pose = camera.pose
            val translation = pose.translation
            val quaternion = pose.rotationQuaternion
            val anchors = JSONArray()
            frame.acquirePointCloud().use { cloud ->
                val points = cloud.points
                var count = 0
                while (points.remaining() >= 4 && count < 96) {
                    val x = points.get(); val y = points.get(); val z = points.get(); val confidence = points.get()
                    if (confidence >= 0.35f) {
                        anchors.put(JSONObject()
                            .put("anchor_id", "ar-point-${cloud.timestamp}-$count")
                            .put("label", "mapped_surface_point")
                            .put("position_m", JSONObject().put("x", x.toDouble()).put("y", y.toDouble()).put("z", z.toDouble()))
                            .put("confidence", confidence.toDouble())
                            .put("persistent", false))
                    }
                    count++
                }
            }
            SensoriumSpatialBridge.update(JSONObject()
                .put("tracking", "tracking")
                .put("depth_available", depthAvailable)
                .put("room_mesh_available", false)
                .put("camera_pose", JSONObject()
                    .put("translation_m", JSONArray().put(translation[0].toDouble()).put(translation[1].toDouble()).put(translation[2].toDouble()))
                    .put("rotation_quaternion", JSONArray().put(quaternion[0].toDouble()).put(quaternion[1].toDouble()).put(quaternion[2].toDouble()).put(quaternion[3].toDouble())))
                .put("anchors", anchors)
                .put("local_processing", true))
        } catch (_: Exception) { }
    }
}
