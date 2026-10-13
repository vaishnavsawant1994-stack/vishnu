package ai.personal.companion

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ManagedByteStoreInstrumentedTest {
    @Test
    fun managedObjectsAreNonBackupIdentityAddressedAndChunkBounded() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val store = ManagedByteStore(context)
        val id = "file:android:${System.nanoTime()}"
        val payload = "hello private android bytes".toByteArray()
        store.putForLocalUse(id, 1, payload)
        try {
            val first = store.readChunk(id, 1, 0, 5)
            assertEquals("hello", String(android.util.Base64.decode(first.getString("bytes_b64"), android.util.Base64.DEFAULT)))
            assertFalse(first.getBoolean("eof"))
            val rest = store.readChunk(id, 1, 5, 1024)
            assertTrue(rest.getBoolean("eof"))
            assertFalse(rest.getBoolean("backup_allowed"))
            assertEquals("no_store", rest.getString("cache_policy"))
            assertThrows(IllegalArgumentException::class.java) { store.readChunk(id, 1, -1, 8) }
            assertThrows(IllegalArgumentException::class.java) { store.readChunk(id, 1, 0, ManagedByteStore.MAX_CHUNK_BYTES + 1) }
        } finally {
            assertTrue(store.delete(id, 1))
        }
    }

    @Test
    fun arbitraryPathsAreNeverAcceptedAsReadAuthority() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val store = ManagedByteStore(context)
        val pathLikeId = "../../private/system/file"
        val bytes = "managed only".toByteArray()
        store.putForLocalUse(pathLikeId, 1, bytes)
        try {
            val result = store.readChunk(pathLikeId, 1, 0, 1024)
            assertEquals("managed only", String(android.util.Base64.decode(result.getString("bytes_b64"), android.util.Base64.DEFAULT)))
            assertFalse(result.has("path"))
        } finally {
            store.delete(pathLikeId, 1)
        }
    }
}
