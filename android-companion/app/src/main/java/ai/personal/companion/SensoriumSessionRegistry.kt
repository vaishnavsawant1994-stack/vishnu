package ai.personal.companion

import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

object SensoriumSessionRegistry {
    data class Grant(
        val sensor: String,
        val resourceId: String,
        val sessionId: String,
        val expiresAtMs: Long,
        val reason: String,
    )

    private val grants = ConcurrentHashMap<String, Grant>()

    private fun key(sensor: String, resourceId: String) = "${sensor.lowercase()}|$resourceId"

    fun grant(sensor: String, resourceId: String = "*", ttlMs: Long = 5 * 60_000L, reason: String = "Owner approved Sensorium") : Grant {
        val safeSensor = sensor.trim().lowercase().take(40)
        val safeResource = resourceId.trim().ifBlank { "*" }.take(240)
        require(safeSensor.isNotBlank()) { "Sensor is required" }
        val boundedTtl = ttlMs.coerceIn(30_000L, 30 * 60_000L)
        val grant = Grant(
            sensor = safeSensor,
            resourceId = safeResource,
            sessionId = UUID.randomUUID().toString(),
            expiresAtMs = System.currentTimeMillis() + boundedTtl,
            reason = reason.take(240),
        )
        grants[key(safeSensor, safeResource)] = grant
        return grant
    }

    fun get(sensor: String, resourceId: String = "*"): Grant? {
        val safeSensor = sensor.trim().lowercase()
        val safeResource = resourceId.trim().ifBlank { "*" }
        val exact = grants[key(safeSensor, safeResource)] ?: if (safeResource != "*") grants[key(safeSensor, "*")] else null
        if (exact != null && exact.expiresAtMs <= System.currentTimeMillis()) {
            grants.remove(key(exact.sensor, exact.resourceId))
            return null
        }
        return exact
    }

    fun require(sensor: String, resourceId: String = "*"): Grant =
        get(sensor, resourceId) ?: throw IllegalStateException("Open Vishnu and allow $sensor for this session first")

    fun revoke(sensor: String, resourceId: String = "*") {
        val safeSensor = sensor.trim().lowercase()
        val safeResource = resourceId.trim().ifBlank { "*" }
        grants.remove(key(safeSensor, safeResource))
        if (safeResource == "*") {
            grants.keys.filter { it.startsWith("$safeSensor|") }.forEach { grants.remove(it) }
        }
    }

    fun stopAll(): Int {
        val count = grants.size
        grants.clear()
        return count
    }

    fun active(): List<Grant> {
        val now = System.currentTimeMillis()
        grants.entries.removeIf { it.value.expiresAtMs <= now }
        return grants.values.sortedBy { it.sensor }
    }

    fun proof(sensor: String, resourceId: String = "*"): JSONObject {
        val grant = require(sensor, resourceId)
        return JSONObject()
            .put("sensor", grant.sensor)
            .put("resource_id", grant.resourceId)
            .put("sensor_session_id", grant.sessionId)
            .put("expires_at_epoch", grant.expiresAtMs / 1000.0)
            .put("local_consent", true)
            .put("reason", grant.reason)
    }
}
