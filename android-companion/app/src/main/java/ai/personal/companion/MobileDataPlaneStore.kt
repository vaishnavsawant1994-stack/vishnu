package ai.personal.companion

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONObject

/**
 * Local-first Vishnu metadata/progress store for the Android companion.
 *
 * It intentionally stores no bearer tokens, provider credentials or raw file
 * bytes. Device-only file bytes stay in their original Android location; this
 * database only keeps bounded continuation metadata that may be synchronized.
 */
class MobileDataPlaneStore(context: Context) : SQLiteOpenHelper(context, "vishnu-data-plane.db", null, 1) {
  companion object {
    private const val MAX_JSON_BYTES = 64 * 1024
    private val PROGRESS_FIELDS = setOf(
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
  }

  override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

  private fun normalizedKey(value: String) = value.trim().lowercase().replace('-', '_').replace(' ', '_')

  private fun containsBlocked(value: Any?, depth: Int = 0): Boolean {
    if (depth > 8) return true
    return when (value) {
      is JSONObject -> value.keys().asSequence().any { raw ->
        val key = normalizedKey(raw)
        key in BLOCKED_KEYS || key.endsWith("_password") || key.endsWith("_secret") ||
          key.endsWith("_token") || key.endsWith("_credential") || containsBlocked(value.opt(raw), depth + 1)
      }
      is org.json.JSONArray -> (0 until value.length()).any { containsBlocked(value.opt(it), depth + 1) }
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

  @Synchronized
  fun putProgress(globalId: String, entityType: String, version: Long, payload: JSONObject): JSONObject {
    require(globalId.isNotBlank() && globalId.length <= 240) { "invalid global_id" }
    require(entityType.isNotBlank() && entityType.length <= 120) { "invalid entity_type" }
    require(version >= 1) { "version must be positive" }
    val clean = progressProjection(payload)
    val existing = get(globalId)
    if (existing != null && version < existing.optLong("version")) {
      return JSONObject().put("applied", false).put("conflict", true).put("local_version", existing.optLong("version"))
    }
    val values = ContentValues().apply {
      put("global_id", globalId)
      put("entity_type", entityType)
      put("storage_policy", "progress_only")
      put("version", version)
      put("payload_json", clean.toString())
      put("tombstone", 0)
      put("updated_at", System.currentTimeMillis())
    }
    writableDatabase.insertWithOnConflict("items", null, values, SQLiteDatabase.CONFLICT_REPLACE)
    return JSONObject().put("applied", true).put("global_id", globalId).put("version", version).put("payload", clean)
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
    val values = ContentValues().apply {
      put("version", version)
      put("tombstone", 1)
      put("updated_at", System.currentTimeMillis())
    }
    return writableDatabase.update("items", values, "global_id=?", arrayOf(globalId)) == 1
  }

  fun status(): JSONObject {
    readableDatabase.rawQuery("SELECT COUNT(*), SUM(CASE WHEN tombstone=1 THEN 1 ELSE 0 END) FROM items", null).use { cursor ->
      cursor.moveToFirst()
      return JSONObject()
        .put("items", cursor.getLong(0))
        .put("tombstones", if (cursor.isNull(1)) 0 else cursor.getLong(1))
        .put("raw_file_bytes_stored", false)
        .put("secrets_stored", false)
    }
  }
}
