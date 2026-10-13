package ai.personal.companion

import android.content.Context
import android.util.Base64
import org.json.JSONObject
import java.io.File
import java.io.RandomAccessFile
import java.security.MessageDigest

/** App-private, non-backup storage for Vishnu-managed objects eligible for governed remote reads. */
class ManagedByteStore(context: Context) {
    companion object {
        const val MAX_CHUNK_BYTES = 256 * 1024
        private const val MAX_GLOBAL_ID_LENGTH = 240
    }

    private val root = File(context.noBackupFilesDir, "vishnu-data-objects").apply {
        if (!exists() && !mkdirs()) throw IllegalStateException("Unable to create Vishnu managed-object directory")
    }

    private fun validate(globalId: String, version: Long) {
        require(globalId.isNotBlank() && globalId.length <= MAX_GLOBAL_ID_LENGTH) { "invalid global_id" }
        require(version >= 1) { "object_version must be positive" }
    }

    private fun digest(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

    private fun objectFile(globalId: String, version: Long): File {
        validate(globalId, version)
        val directory = File(root, digest(globalId)).apply {
            if (!exists() && !mkdirs()) throw IllegalStateException("Unable to create Vishnu object directory")
        }
        return File(directory, "v$version.bin")
    }

    /** Internal app workflow only. This method is intentionally not exposed as a DeviceGateway command. */
    fun putForLocalUse(globalId: String, version: Long, bytes: ByteArray) {
        val destination = objectFile(globalId, version)
        val temporary = File(destination.parentFile, ".${destination.name}.tmp")
        temporary.outputStream().use { it.write(bytes) }
        if (!temporary.renameTo(destination)) {
            temporary.delete()
            throw IllegalStateException("Unable to atomically persist Vishnu managed object")
        }
    }

    fun readChunk(globalId: String, version: Long, offset: Long, length: Int): JSONObject {
        validate(globalId, version)
        require(offset >= 0) { "offset must be non-negative" }
        require(length in 1..MAX_CHUNK_BYTES) { "length exceeds governed chunk limit" }
        val file = objectFile(globalId, version)
        if (!file.isFile) throw IllegalArgumentException("managed Vishnu object is unavailable")
        RandomAccessFile(file, "r").use { raf ->
            val total = raf.length()
            require(offset <= total) { "offset exceeds object size" }
            raf.seek(offset)
            val wanted = minOf(length.toLong(), total - offset).toInt()
            val buffer = ByteArray(wanted)
            val read = if (wanted == 0) 0 else raf.read(buffer)
            val count = maxOf(read, 0)
            val bytes = if (count == buffer.size) buffer else buffer.copyOf(count)
            return JSONObject()
                .put("bytes_b64", Base64.encodeToString(bytes, Base64.NO_WRAP))
                .put("bytes_read", count)
                .put("offset", offset)
                .put("object_size", total)
                .put("eof", offset + count >= total)
                .put("cache_policy", "no_store")
                .put("backup_allowed", false)
        }
    }

    fun delete(globalId: String, version: Long): Boolean {
        val file = objectFile(globalId, version)
        return !file.exists() || file.delete()
    }
}
