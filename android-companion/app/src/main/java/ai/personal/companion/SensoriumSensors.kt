package ai.personal.companion

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.round

object SensoriumSensors {
    private const val SAMPLE_TIMEOUT_MS = 900L

    private fun permission(context: Context, name: String): Boolean =
        ContextCompat.checkSelfPermission(context, name) == PackageManager.PERMISSION_GRANTED

    private fun sensorManager(context: Context) = context.getSystemService(SensorManager::class.java)

    private fun oneSample(context: Context, type: Int): FloatArray? {
        val manager = sensorManager(context)
        val sensor = manager.getDefaultSensor(type) ?: return null
        val result = AtomicReference<FloatArray?>(null)
        val latch = CountDownLatch(1)
        val listener = object : SensorEventListener {
            override fun onSensorChanged(event: SensorEvent) {
                result.compareAndSet(null, event.values.copyOf())
                latch.countDown()
            }
            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
        }
        manager.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_NORMAL)
        try { latch.await(SAMPLE_TIMEOUT_MS, TimeUnit.MILLISECONDS) } finally { manager.unregisterListener(listener) }
        return result.get()
    }

    private fun arr(values: FloatArray?): JSONArray? {
        if (values == null) return null
        val out = JSONArray()
        values.take(8).forEach { out.put(round(it * 10_000.0) / 10_000.0) }
        return out
    }

    private fun motion(context: Context): JSONObject {
        val accel = oneSample(context, Sensor.TYPE_ACCELEROMETER)
        val gyro = oneSample(context, Sensor.TYPE_GYROSCOPE)
        val magnetic = oneSample(context, Sensor.TYPE_MAGNETIC_FIELD)
        val rotation = oneSample(context, Sensor.TYPE_ROTATION_VECTOR)
        val gravity = oneSample(context, Sensor.TYPE_GRAVITY)
        val linear = oneSample(context, Sensor.TYPE_LINEAR_ACCELERATION)
        val orientation = if (rotation != null) {
            val matrix = FloatArray(9)
            val values = FloatArray(3)
            SensorManager.getRotationMatrixFromVector(matrix, rotation)
            SensorManager.getOrientation(matrix, values)
            JSONArray().put(Math.toDegrees(values[0].toDouble())).put(Math.toDegrees(values[1].toDouble())).put(Math.toDegrees(values[2].toDouble()))
        } else null
        return JSONObject()
            .put("accelerometer_m_s2", arr(accel) ?: JSONObject.NULL)
            .put("gyroscope_rad_s", arr(gyro) ?: JSONObject.NULL)
            .put("magnetic_field_ut", arr(magnetic) ?: JSONObject.NULL)
            .put("gravity_m_s2", arr(gravity) ?: JSONObject.NULL)
            .put("linear_acceleration_m_s2", arr(linear) ?: JSONObject.NULL)
            .put("orientation_deg_yaw_pitch_roll", orientation ?: JSONObject.NULL)
            .put("activity_hint", activityHint(context))
            .put("captured_at", System.currentTimeMillis() / 1000.0)
            .put("freshness_seconds", 5.0)
            .put("confidence", if (accel != null || gyro != null) 0.85 else 0.3)
    }

    private fun activityHint(context: Context): String {
        val step = oneSample(context, Sensor.TYPE_STEP_DETECTOR)
        if (step?.firstOrNull()?.let { it > 0f } == true) return "step_detected"
        val accel = oneSample(context, Sensor.TYPE_LINEAR_ACCELERATION) ?: return "unknown"
        val magnitude = kotlin.math.sqrt(accel.take(3).sumOf { (it * it).toDouble() })
        return when {
            magnitude > 4.0 -> "high_motion"
            magnitude > 0.8 -> "moving"
            else -> "stationary_likely"
        }
    }

    private fun environment(context: Context): JSONObject {
        val light = oneSample(context, Sensor.TYPE_LIGHT)?.firstOrNull()
        val proximity = oneSample(context, Sensor.TYPE_PROXIMITY)?.firstOrNull()
        val pressure = oneSample(context, Sensor.TYPE_PRESSURE)?.firstOrNull()
        val ambient = oneSample(context, Sensor.TYPE_AMBIENT_TEMPERATURE)?.firstOrNull()
        val humidity = oneSample(context, Sensor.TYPE_RELATIVE_HUMIDITY)?.firstOrNull()
        val power = context.getSystemService(PowerManager::class.java)
        val battery = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        return JSONObject()
            .put("ambient_light_lux", light ?: JSONObject.NULL)
            .put("proximity_cm", proximity ?: JSONObject.NULL)
            .put("pressure_hpa", pressure ?: JSONObject.NULL)
            .put("ambient_temperature_c", ambient ?: JSONObject.NULL)
            .put("relative_humidity_percent", humidity ?: JSONObject.NULL)
            .put("thermal_status", if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) power.currentThermalStatus else -1)
            .put("battery_percent", battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY))
            .put("captured_at", System.currentTimeMillis() / 1000.0)
            .put("freshness_seconds", 15.0)
            .put("confidence", 0.85)
    }

    private fun network(context: Context): JSONObject {
        val manager = context.getSystemService(ConnectivityManager::class.java)
        val network = manager.activeNetwork
        val caps = network?.let { manager.getNetworkCapabilities(it) }
        val transports = JSONArray()
        if (caps != null) {
            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) transports.put("wifi")
            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) transports.put("cellular")
            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) transports.put("ethernet")
            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) transports.put("vpn")
            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_BLUETOOTH)) transports.put("bluetooth")
        }
        return JSONObject()
            .put("connected", caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true)
            .put("validated", caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true)
            .put("metered", manager.isActiveNetworkMetered)
            .put("transports", transports)
            .put("downstream_kbps", caps?.linkDownstreamBandwidthKbps ?: -1)
            .put("upstream_kbps", caps?.linkUpstreamBandwidthKbps ?: -1)
            .put("captured_at", System.currentTimeMillis() / 1000.0)
            .put("freshness_seconds", 30.0)
            .put("confidence", 0.95)
    }

    private fun location(context: Context): JSONObject {
        val fine = permission(context, Manifest.permission.ACCESS_FINE_LOCATION)
        val coarse = permission(context, Manifest.permission.ACCESS_COARSE_LOCATION)
        if (!fine && !coarse) {
            return JSONObject().put("available", false).put("permission", "not_granted")
                .put("captured_at", System.currentTimeMillis() / 1000.0).put("confidence", 0.0)
        }
        val manager = context.getSystemService(LocationManager::class.java)
        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER, LocationManager.PASSIVE_PROVIDER)
        var best: Location? = null
        for (provider in providers) {
            val candidate = try { manager.getLastKnownLocation(provider) } catch (_: SecurityException) { null }
            if (candidate != null && (best == null || candidate.time > best!!.time)) best = candidate
        }
        val loc = best ?: return JSONObject().put("available", false).put("permission", if (fine) "fine" else "coarse")
            .put("captured_at", System.currentTimeMillis() / 1000.0).put("confidence", 0.25)
        return JSONObject()
            .put("available", true)
            .put("permission", if (fine) "fine" else "coarse")
            .put("latitude", loc.latitude)
            .put("longitude", loc.longitude)
            .put("accuracy_m", loc.accuracy.toDouble())
            .put("altitude_m", if (loc.hasAltitude()) loc.altitude else JSONObject.NULL)
            .put("bearing_deg", if (loc.hasBearing()) loc.bearing.toDouble() else JSONObject.NULL)
            .put("speed_m_s", if (loc.hasSpeed()) loc.speed.toDouble() else JSONObject.NULL)
            .put("captured_at", loc.time / 1000.0)
            .put("freshness_seconds", 60.0)
            .put("confidence", when { loc.accuracy <= 20f -> 0.95; loc.accuracy <= 100f -> 0.8; else -> 0.55 })
    }

    fun inventory(context: Context): JSONObject {
        val manager = sensorManager(context)
        val available = manager.getSensorList(Sensor.TYPE_ALL).map { it.type }.toSet()
        fun has(type: Int) = available.contains(type)
        return JSONObject()
            .put("location", JSONObject().put("available", context.packageManager.hasSystemFeature(PackageManager.FEATURE_LOCATION)).put("fine_permission", permission(context, Manifest.permission.ACCESS_FINE_LOCATION)).put("coarse_permission", permission(context, Manifest.permission.ACCESS_COARSE_LOCATION)))
            .put("motion", JSONObject().put("accelerometer", has(Sensor.TYPE_ACCELEROMETER)).put("gyroscope", has(Sensor.TYPE_GYROSCOPE)).put("magnetometer", has(Sensor.TYPE_MAGNETIC_FIELD)).put("rotation_vector", has(Sensor.TYPE_ROTATION_VECTOR)).put("step_detector", has(Sensor.TYPE_STEP_DETECTOR)))
            .put("environment", JSONObject().put("light", has(Sensor.TYPE_LIGHT)).put("proximity", has(Sensor.TYPE_PROXIMITY)).put("barometer", has(Sensor.TYPE_PRESSURE)).put("ambient_temperature", has(Sensor.TYPE_AMBIENT_TEMPERATURE)).put("humidity", has(Sensor.TYPE_RELATIVE_HUMIDITY)))
            .put("network", JSONObject().put("available", true))
            .put("battery", JSONObject().put("available", true))
            .put("screen", JSONObject().put("media_projection", Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP))
            .put("microphone", JSONObject().put("available", context.packageManager.hasSystemFeature(PackageManager.FEATURE_MICROPHONE)).put("permission", permission(context, Manifest.permission.RECORD_AUDIO)))
            .put("document", JSONObject().put("local_ocr", true).put("barcode", true))
            .put("spatial", JSONObject().put("arcore_adapter", true).put("depth", context.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY)))
            .put("captured_at", System.currentTimeMillis() / 1000.0)
    }

    fun snapshot(context: Context, requested: JSONArray): JSONObject {
        val sensors = JSONObject()
        for (i in 0 until requested.length().coerceAtMost(16)) {
            when (val kind = requested.optString(i).lowercase()) {
                "location" -> sensors.put(kind, location(context))
                "motion" -> sensors.put(kind, motion(context))
                "environment" -> sensors.put(kind, environment(context))
                "network" -> sensors.put(kind, network(context))
                else -> Unit
            }
        }
        val sessions = JSONObject()
        listOf("location", "motion", "environment", "network").forEach { kind ->
            SensoriumSessionRegistry.get(kind)?.let { sessions.put(kind, SensoriumSessionRegistry.proof(kind)) }
        }
        return JSONObject().put("sensors", sensors).put("sessions", sessions)
    }
}
