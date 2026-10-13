package ai.personal.companion

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * Local-first Vishnu metadata/progress store for the Android companion.
 *
 * It intentionally stores no bearer tokens, provider credentials or raw file
 * bytes. Device-only file bytes stay in their original Android location; this
 * database only keeps bounded continuation metadata that may be synchronized.
 * Locally-originated progress changes are journaled in an outbox and are only
 * removed after the canonical Vishnu runtime durably acknowledges them.
 */
class MobileDataPlaneStore(context: Context) : SQLiteOpenHelper(context, "vishnu-data-plane.db", null, 2) {
  companion object {
    private const val MAX_JSON_BYTES = 64 * 1024
    private val PROGRESS_FIELDS = linkedSetOf(
      "project_id", "project_name", "status", "progress", "task_id", "task_title",
      "task_status", "milestone_id", "milestone_title", "milestone_status",
      "last_step", "next_step", "last_activity", "allowed_notes", "updated_at"
    )
    private val BLOCKED_KEYS = setOf(
      "password", "passwd", "passphrase", "secret", "token", "access_token", "refresh_token",
      "api_key", "apikey", "authorization", "cookie", "credential", "private_key",
      "session_token", "bearer_token", "bytes", "content_bytes", "raw", "raw_bytes",
      "raw_content", "file_bytes", "image_bytes", "audio_bytes", "video_bytes", "document_content"
    )
  }

  override fun onCreate(db: SQLiteDatabase) {
    db.execSQL(
      """CREATE TABLE items(
        global_id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        storage_policy TEXT NOT NULL,
        version INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        tombstone INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL
      )""".trimIndent()
    )
    createOutbox(db)
  }

  private fun createOutbox(db: SQLiteDatabase) {
    db.execSQL(
      """CREATE TABLE IF NOT EXISTS outbox(
        source_event_id TEXT PRIMARY KEY,
        global_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        version INTEGER NOT NULL,
        event_kind TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at INTEGER NOT NULL
      )""".trimIndent()
    )
    db.execSQL("CREATE INDEX IF NOT EXISTS idx_outbox_created ON outbox(created_at, source_event_id)")
  }

  override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
    if (oldVersion < 2) createOutbox(db)
  }

  private fun normalizedKey(value: String) = value.trim().lowercase().replace('-', '_').replace(' ', '_')

  private fun containsBlocked(value: Any?, depth: Int = 0): Boolean {
    if (depth > 8) return true
    return when (value) {
      is JSONObject -> value.keys().asSequence().any { raw ->
        val key = normalizedKey(raw)
        key in BLOCKED_KEYS || key.endsWith("_password") || key.endsWith("_secret") ||
          key.endsWith("_token") || key.endsWith("_credential") || containsBlocked(value.opt(raw), depth + 1)
      }
      is JSONArray -> (0 until value.length()).any { containsBlocked(value.opt(it), depth + 1) }
      else -> false
    }
  }

  private fun progressProjection(input: JSONObject): JSONObject {
    if (containsBlocked(input)) throw IllegalArgumentException("progress payload contains prohibited secret/raw-content fields")
    val output = JSONObject()
    for (key in PROGRESS_FIELDS) if (input.has(key)) output.put(key, input.get(key))
    val encoded = output.toString().toByteArray(Charsets.UTF_8)
    if (encoded.size > MAX_JSON_BYTES) throw IllegalArgumentException("progress payload is too large")
    return output
  }

  private fun samePayload(left: JSONObject, right: JSONObject): Boolean = left.similar(right)

  @Synchronized
  fun putProgress(globalId: String, entityType: String, version: Long, payload: JSONObject): JSONObject {
    require(globalId.isNotBlank() && globalId.length <= 240) { "invalid global_id" }
    require(entityType.isNotBlank() && entityType.length <= 120) { "invalid entity_type" }
    require(version >= 1) { "version must be positive" }
    val clean = progressProjection(payload)
    val existing = get(globalId)
    if (existing != null) {
      val localVersion = existing.optLong("version")
      if (version < localVersion || (version == localVersion && !samePayload(existing.optJSONObject("payload") ?: JSONObject(), clean))) {
        return JSONObject().put("applied", false).put("conflict", true).put("local_version", localVersion)
      }
      if (version == localVersion && samePayload(existing.optJSONObject("payload") ?: JSONObject(), clean) && !existing.optBoolean("tombstone")) {
        return JSONObject().put("applied", true).put("duplicate", true).put("global_id", globalId).put("version", version).put("payload", clean)
      }
    }
    persistItem(globalId, entityType, version, clean, false)
    return JSONObject().put("applied", true).put("global_id", globalId).put("version", version).put("payload", clean)
  }

  private fun persistItem(globalId: String, entityType: String, version: Long, payload: JSONObject, tombstone: Boolean) {
    val values = ContentValues().apply {
      put("global_id", globalId)
      put("entity_type", entityType)
      put("storage_policy", "progress_only")
      put("version", version)
      put("payload_json", payload.toString())
      put("tombstone", if (tombstone) 1 else 0)
      put("updated_at", System.currentTimeMillis())
    }
    writableDatabase.insertWithOnConflict("items", null, values, SQLiteDatabase.CONFLICT_REPLACE)
  }

  /** Record a real local/offline edit for later phone -> Vishnu synchronization. */
  @Synchronized
  fun putLocalProgress(globalId: String, entityType: String, payload: JSONObject): JSONObject {
    require(globalId.isNotBlank() && globalId.length <= 240) { "invalid global_id" }
    require(entityType.isNotBlank() && entityType.length <= 120) { "invalid entity_type" }
    val clean = progressProjection(payload)
    val nextVersion = (get(globalId)?.optLong("version") ?: 0L) + 1L
    persistItem(globalId, entityType, nextVersion, clean, false)
    val sourceEventId = UUID.randomUUID().toString()
    val values = ContentValues().apply {
      put("source_event_id", sourceEventId)
      put("global_id", globalId)
      put("entity_type", entityType)
      put("version", nextVersion)
      put("event_kind", "update")
      put("payload_json", clean.toString())
      put("created_at", System.currentTimeMillis())
    }
    writableDatabase.insertOrThrow("outbox", null, values)
    return JSONObject().put("applied", true).put("source_event_id", sourceEventId).put("global_id", globalId).put("version", nextVersion).put("payload", clean)
  }

  @Synchronized
  fun get(globalId: String): JSONObject? {
    readableDatabase.query(
      "items", arrayOf("global_id", "entity_type", "storage_policy", "version", "payload_json", "tombstone", "updated_at"),
      "global_id=?", arrayOf(globalId), null, null, null, "1"
    ).use { cursor ->
      if (!cursor.moveToFirst()) return null
      return JSONObject()
        .put("global_id", cursor.getString(0))
        .put("entity_type", cursor.getString(1))
        .put("storage_policy", cursor.getString(2))
        .put("version", cursor.getLong(3))
        .put("payload", JSONObject(cursor.getString(4)))
        .put("tombstone", cursor.getInt(5) != 0)
        .put("updated_at_ms", cursor.getLong(6))
    }
  }

  @Synchronized
  fun tombstone(globalId: String, version: Long): Boolean {
    val current = get(globalId) ?: return false
    if (version < current.optLong("version")) return false
    if (version == current.optLong("version") && !current.optBoolean("tombstone")) return false
    val values = ContentValues().apply {
      put("version", version)
      put("tombstone", 1)
      put("updated_at", System.currentTimeMillis())
    }
    return writableDatabase.update("items", values, "global_id=?", arrayOf(globalId)) == 1
  }

  @Synchronized
  fun tombstoneLocal(globalId: String): JSONObject {
    val current = get(globalId) ?: throw IllegalArgumentException("data-plane item not found")
    val nextVersion = current.getLong("version") + 1L
    val payload = current.optJSONObject("payload") ?: JSONObject()
    persistItem(globalId, current.getString("entity_type"), nextVersion, payload, true)
    val sourceEventId = UUID.randomUUID().toString()
    val values = ContentValues().apply {
      put("source_event_id", sourceEventId)
      put("global_id", globalId)
      put("entity_type", current.getString("entity_type"))
      put("version", nextVersion)
      put("event_kind", "delete")
      put("payload_json", JSONObject().put("updated_at", System.currentTimeMillis()).toString())
      put("created_at", System.currentTimeMillis())
    }
    writableDatabase.insertOrThrow("outbox", null, values)
    return JSONObject().put("deleted", true).put("source_event_id", sourceEventId).put("global_id", globalId).put("version", nextVersion)
  }

  @Synchronized
  fun pending(limit: Int = 100): JSONObject {
    val bounded = limit.coerceIn(1, 500)
    val events = JSONArray()
    readableDatabase.query(
      "outbox",
      arrayOf("source_event_id", "global_id", "entity_type", "version", "event_kind", "payload_json", "created_at"),
      null, null, null, null, "created_at ASC, source_event_id ASC", bounded.toString()
    ).use { cursor ->
      while (cursor.moveToNext()) {
        events.put(JSONObject()
          .put("source_event_id", cursor.getString(0))
          .put("global_id", cursor.getString(1))
          .put("entity_type", cursor.getString(2))
          .put("storage_policy", "progress_only")
          .put("version", cursor.getLong(3))
          .put("event_kind", cursor.getString(4))
          .put("payload", JSONObject(cursor.getString(5)))
          .put("created_at_ms", cursor.getLong(6)))
      }
    }
    return JSONObject().put("events", events)
  }

  @Synchronized
  fun acknowledge(sourceEventId: String): Boolean {
    require(sourceEventId.isNotBlank()) { "source_event_id is required" }
    return writableDatabase.delete("outbox", "source_event_id=?", arrayOf(sourceEventId)) == 1
  }

  fun status(): JSONObject {
    readableDatabase.rawQuery(
      "SELECT (SELECT COUNT(*) FROM items), (SELECT COUNT(*) FROM items WHERE tombstone=1), (SELECT COUNT(*) FROM outbox)", null
    ).use { cursor ->
      cursor.moveToFirst()
      return JSONObject()
        .put("items", cursor.getLong(0))
        .put("tombstones", cursor.getLong(1))
        .put("pending_local_events", cursor.getLong(2))
        .put("raw_file_bytes_stored", false)
        .put("secrets_stored", false)
    }
  }
}
