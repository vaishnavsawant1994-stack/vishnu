package ai.personal.companion

import android.content.Context
import android.graphics.BitmapFactory
import android.util.Base64
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.pose.PoseDetection
import com.google.mlkit.vision.pose.PoseLandmark
import com.google.mlkit.vision.pose.defaults.PoseDetectorOptions
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.sqrt

object SensoriumVisualLocal {
    private fun imageFromVision(context: Context, requireDocumentSession: Boolean): Pair<InputImage, JSONObject> {
        if (requireDocumentSession) SensoriumSessionRegistry.require("document", "*")
        val camera = VisionCameraBridge.snapshot(context, JSONObject().put("max_edge", 1280))
        val bytes = Base64.decode(camera.getString("base64"), Base64.DEFAULT)
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            ?: throw IllegalStateException("Privacy-processed camera frame could not be decoded")
        return Pair(InputImage.fromBitmap(bitmap, 0), camera)
    }

    fun documentExtract(context: Context): JSONObject {
        val grant = SensoriumSessionRegistry.require("document", "*")
        val (image, camera) = imageFromVision(context, true)
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        val scanner = BarcodeScanning.getClient()
        val textRef = AtomicReference("")
        val barcodeRef = AtomicReference(JSONArray())
        val latch = CountDownLatch(2)
        recognizer.process(image)
            .addOnSuccessListener { result -> textRef.set(result.text.take(100_000)); latch.countDown() }
            .addOnFailureListener { latch.countDown() }
        scanner.process(image)
            .addOnSuccessListener { codes ->
                val rows = JSONArray()
                codes.take(64).forEach { barcode ->
                    rows.put(JSONObject().put("format", barcode.format).put("value", (barcode.rawValue ?: "").take(4096)))
                }
                barcodeRef.set(rows); latch.countDown()
            }
            .addOnFailureListener { latch.countDown() }
        latch.await(6, TimeUnit.SECONDS)
        recognizer.close(); scanner.close()
        return JSONObject()
            .put("text", textRef.get())
            .put("barcodes", barcodeRef.get())
            .put("fields", JSONObject())
            .put("handwriting", false)
            .put("confidence", if (textRef.get().isNotBlank() || barcodeRef.get().length() > 0) 0.9 else 0.45)
            .put("local_extraction", true)
            .put("privacy_processed", true)
            .put("raw_image_retained", false)
            .put("resource_id", grant.resourceId)
            .put("sensor_session_id", grant.sessionId)
            .put("expires_at_epoch", grant.expiresAtMs / 1000.0)
            .put("local_consent", true)
            .put("camera_id", camera.optString("camera_id"))
            .put("captured_at", Instant.now().toEpochMilli() / 1000.0)
    }

    private fun landmarkJson(landmark: PoseLandmark?): JSONObject? {
        landmark ?: return null
        return JSONObject()
            .put("x", landmark.position.x.toDouble())
            .put("y", landmark.position.y.toDouble())
            .put("likelihood", landmark.inFrameLikelihood.toDouble())
    }

    private fun pointing(elbow: PoseLandmark?, wrist: PoseLandmark?, index: PoseLandmark?): JSONObject? {
        if (elbow == null || wrist == null || index == null) return null
        if (minOf(elbow.inFrameLikelihood, wrist.inFrameLikelihood, index.inFrameLikelihood) < 0.5f) return null
        val vx = index.position.x - elbow.position.x
        val vy = index.position.y - elbow.position.y
        val length = sqrt((vx * vx + vy * vy).toDouble())
        if (length < 20.0) return null
        return JSONObject()
            .put("origin", JSONObject().put("x", elbow.position.x.toDouble()).put("y", elbow.position.y.toDouble()))
            .put("through_wrist", JSONObject().put("x", wrist.position.x.toDouble()).put("y", wrist.position.y.toDouble()))
            .put("target_direction", JSONObject().put("x", vx / length).put("y", vy / length))
            .put("confidence", minOf(elbow.inFrameLikelihood, wrist.inFrameLikelihood, index.inFrameLikelihood).toDouble())
    }

    fun poseAndGesture(context: Context): JSONObject {
        val (image, camera) = imageFromVision(context, false)
        val options = PoseDetectorOptions.Builder().setDetectorMode(PoseDetectorOptions.SINGLE_IMAGE_MODE).build()
        val detector = PoseDetection.getClient(options)
        val poseRef = AtomicReference<com.google.mlkit.vision.pose.Pose?>(null)
        val latch = CountDownLatch(1)
        detector.process(image).addOnSuccessListener { poseRef.set(it); latch.countDown() }.addOnFailureListener { latch.countDown() }
        latch.await(5, TimeUnit.SECONDS); detector.close()
        val pose = poseRef.get()
        val landmarks = JSONObject()
        val named = mapOf(
            "left_shoulder" to PoseLandmark.LEFT_SHOULDER,
            "right_shoulder" to PoseLandmark.RIGHT_SHOULDER,
            "left_elbow" to PoseLandmark.LEFT_ELBOW,
            "right_elbow" to PoseLandmark.RIGHT_ELBOW,
            "left_wrist" to PoseLandmark.LEFT_WRIST,
            "right_wrist" to PoseLandmark.RIGHT_WRIST,
            "left_index" to PoseLandmark.LEFT_INDEX,
            "right_index" to PoseLandmark.RIGHT_INDEX,
            "left_thumb" to PoseLandmark.LEFT_THUMB,
            "right_thumb" to PoseLandmark.RIGHT_THUMB,
            "left_hip" to PoseLandmark.LEFT_HIP,
            "right_hip" to PoseLandmark.RIGHT_HIP,
            "left_knee" to PoseLandmark.LEFT_KNEE,
            "right_knee" to PoseLandmark.RIGHT_KNEE,
            "left_ankle" to PoseLandmark.LEFT_ANKLE,
            "right_ankle" to PoseLandmark.RIGHT_ANKLE,
        )
        if (pose != null) named.forEach { (name, type) -> landmarkJson(pose.getPoseLandmark(type))?.let { landmarks.put(name, it) } }
        val leftPoint = if (pose == null) null else pointing(pose.getPoseLandmark(PoseLandmark.LEFT_ELBOW), pose.getPoseLandmark(PoseLandmark.LEFT_WRIST), pose.getPoseLandmark(PoseLandmark.LEFT_INDEX))
        val rightPoint = if (pose == null) null else pointing(pose.getPoseLandmark(PoseLandmark.RIGHT_ELBOW), pose.getPoseLandmark(PoseLandmark.RIGHT_WRIST), pose.getPoseLandmark(PoseLandmark.RIGHT_INDEX))
        return JSONObject()
            .put("pose_detected", pose != null && landmarks.length() >= 4)
            .put("landmarks", landmarks)
            .put("left_pointing", leftPoint ?: JSONObject.NULL)
            .put("right_pointing", rightPoint ?: JSONObject.NULL)
            .put("camera_id", camera.optString("camera_id"))
            .put("local_processing", true)
            .put("privacy_processed", true)
            .put("raw_frame_retained", false)
            .put("execution_authority", false)
            .put("captured_at", Instant.now().toEpochMilli() / 1000.0)
    }
}
