package ai.personal.companion

import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList

object SensoriumSessionRegistry {
    data class Grant(
        val sensor: String,
        val resourceId: String,
        val sessionId: String,
        val expiresAtMs: Long,
        val reason: String,
    )

    data class AuditEntry(
        val createdAtMs: Long,
        val action: String,
        val sensor: String,
        val resourceId: String,
        val reason: String,
    )

    private val grants = ConcurrentHashMap<String, Grant>()
    private val audit = CopyOnWriteArrayList<AuditEntry>()

    private fun key(sensor: String, resourceId: String) = "${sensor.lowercase()}|$resourceId"

    private fun record(action: String, sensor: String, resourceId: String, reason: String) {
        audit.add(
            AuditEntry(
                createdAtMs = System.currentTimeMillis(),
                action = action.take(40),
                sensor = sensor.take(40),
                resourceId = resourceId.take(240),
                reason = reason.take(240),
            )
        )
        while (audit.size > 100) audit.removeAt(0)
    }

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
        record("session_granted", safeSensor, safeResource, grant.reason)
        return grant
    }

    fun get(sensor: String, resourceId: String = "*"): Grant? {
        val safeSensor = sensor.trim().lowercase()
        val safeResource = resourceId.trim().ifBlank { "*" }
        val exact = grants[key(safeSensor, safeResource)] ?: if (safeResource != "*") grants[key(safeSensor, "*")] else null
        if (exact != null && exact.expiresAtMs <= System.currentTimeMillis()) {
            grants.remove(key(exact.sensor, exact.resourceId))
            record("session_expired", exact.sensor, exact.resourceId, "Temporary sensor session expired")
            return null
        }
        return exact
    }

    fun require(sensor: String, resourceId: String = "*"): Grant =
        get(sensor, resourceId) ?: throw IllegalStateException("Open Vishnu and allow $sensor for this session first")

    fun revoke(sensor: String, resourceId: String = "*") {
        val safeSensor = sensor.trim().lowercase()
        val safeResource = resourceId.trim().ifBlank { "*" }
        val removed = mutableListOf<Grant>()
        grants.remove(key(safeSensor, safeResource))?.let { removed.add(it) }
        if (safeResource == "*") {
            grants.keys.filter { it.startsWith("$safeSensor|") }.forEach { key ->
                grants.remove(key)?.let { removed.add(it) }
            }
        }
        if (removed.isEmpty()) {
            record("session_revoke_requested", safeSensor, safeResource, "No active local session remained")
        } else {
            removed.distinctBy { it.sessionId }.forEach {
                record("session_revoked", it.sensor, it.resourceId, "Owner stopped sensor session")
            }
        }
    }

    fun stopAll(): Int {
        val rows = grants.values.toList()
        grants.clear()
        rows.forEach { record("stop_all", it.sensor, it.resourceId, "Owner stopped all sensing") }
        if (rows.isEmpty()) record("stop_all", "all", "*", "Owner stopped all sensing; no active sessions")
        return rows.size
    }

    fun active(): List<Grant> {
        val now = System.currentTimeMillis()
        val expired = grants.values.filter { it.expiresAtMs <= now }
        expired.forEach {
            grants.remove(key(it.sensor, it.resourceId))
            record("session_expired", it.sensor, it.resourceId, "Temporary sensor session expired")
        }
        return grants.values.sortedBy { it.sensor }
    }

    fun recentAudit(limit: Int = 25): List<AuditEntry> = audit.takeLast(limit.coerceIn(1, 100)).reversed()

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
