package ai.personal.companion

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SmokeInstrumentedTest {
    @Test
    fun appContextAndOnboardingActivitiesExist() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        assertEquals("ai.personal.companion", context.packageName)
        assertNotNull(Class.forName("ai.personal.companion.DeviceCommandService"))
        assertNotNull(Class.forName("ai.personal.companion.ConnectActivity"))
        assertNotNull(Class.forName("ai.personal.companion.MainActivity"))
        assertNotNull(Class.forName("ai.personal.companion.VishnuDiscovery"))
        assertNotNull(Class.forName("ai.personal.companion.PinnedTls"))
        assertNotNull(Class.forName("ai.personal.companion.MobileDataPlaneStore"))
    }

    @Test
    fun pairingQrParsesAndNormalizesOrigin() {
        val token = "a".repeat(32)
        val raw = "vishnu://pair?v=1&base=https%3A%2F%2Fvishnu.example.test%2Fignored&token=$token&code=123456&expires=9999999999"
        val payload = PairingPayloadParser.parse(raw, nowMillis = 100_000)
        assertEquals(1, payload.version)
        assertEquals("https://vishnu.example.test", payload.baseUrl)
        assertEquals(token, payload.token)
        assertEquals("123456", payload.code)
    }

    @Test
    fun zeroConfigPairingQrCarriesServiceAndTlsPinWithoutAddress() {
        val token = "b".repeat(32)
        val service = "0123456789abcdef0123456789abcdef"
        val pin = "ab".repeat(32)
        val raw = "vishnu://pair?v=2&service=$service&fp=$pin&token=$token&code=654321&expires=9999999999&fallback=https%3A%2F%2Frelay.example.test"
        val payload = PairingPayloadParser.parse(raw, nowMillis = 100_000)
        assertTrue(payload.zeroConfig)
        assertNull(payload.baseUrl)
        assertEquals(service, payload.serviceId)
        assertEquals(pin, payload.certSha256)
        assertEquals("https://relay.example.test", payload.fallbackUrl)
        assertEquals(pin, PinnedTls.normalizeFingerprint(pin.uppercase()))
    }

    @Test
    fun pairingQrRejectsExpiredOfferRemoteHttpAndBadPin() {
        val token = "a".repeat(32)
        val expired = "vishnu://pair?v=1&base=https%3A%2F%2Fvishnu.example.test&token=$token&code=123456&expires=100"
        assertThrows(IllegalArgumentException::class.java) {
            PairingPayloadParser.parse(expired, nowMillis = 101_000)
        }
        assertThrows(IllegalArgumentException::class.java) {
            PairingPayloadParser.normalizeOrigin("http://vishnu.example.test")
        }
        val badPin = "vishnu://pair?v=2&service=0123456789abcdef&fp=bad&token=$token&code=123456&expires=9999999999"
        assertThrows(IllegalArgumentException::class.java) {
            PairingPayloadParser.parse(badPin, nowMillis = 100_000)
        }
        assertEquals(
            "http://localhost:8766",
            PairingPayloadParser.normalizeOrigin("http://localhost:8766/path", allowLocalHttp = true),
        )
    }

    @Test
    fun mobileDataPlaneStoresOnlyAllowedProgressFields() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.deleteDatabase("vishnu-data-plane.db")
        val store = MobileDataPlaneStore(context)
        try {
            val result = store.putProgress(
                "project:android-test",
                "project",
                1,
                JSONObject()
                    .put("project_name", "Rudra")
                    .put("status", "active")
                    .put("next_step", "Finish homepage")
                    .put("private_detail", "must not replicate"),
            )
            assertTrue(result.getBoolean("applied"))
            val payload = result.getJSONObject("payload")
            assertEquals("Rudra", payload.getString("project_name"))
            assertEquals("Finish homepage", payload.getString("next_step"))
            assertFalse(payload.has("private_detail"))
            val status = store.status()
            assertFalse(status.getBoolean("raw_file_bytes_stored"))
            assertFalse(status.getBoolean("secrets_stored"))
        } finally {
            store.close()
            context.deleteDatabase("vishnu-data-plane.db")
        }
    }

    @Test
    fun mobileDataPlaneRejectsSecretsRawBytesAndStaleVersions() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.deleteDatabase("vishnu-data-plane.db")
        val store = MobileDataPlaneStore(context)
        try {
            assertThrows(IllegalArgumentException::class.java) {
                store.putProgress(
                    "project:secret-test",
                    "project",
                    1,
                    JSONObject().put("status", "active").put("api_key", "secret"),
                )
            }
            assertThrows(IllegalArgumentException::class.java) {
                store.putProgress(
                    "project:raw-test",
                    "project",
                    1,
                    JSONObject().put("status", "active").put("file_bytes", "raw"),
                )
            }
            store.putProgress(
                "project:conflict-test",
                "project",
                3,
                JSONObject().put("status", "new"),
            )
            val stale = store.putProgress(
                "project:conflict-test",
                "project",
                2,
                JSONObject().put("status", "old"),
            )
            assertFalse(stale.getBoolean("applied"))
            assertTrue(stale.getBoolean("conflict"))
            assertEquals(3, stale.getLong("local_version"))
            assertTrue(store.tombstone("project:conflict-test", 4))
            assertTrue(store.get("project:conflict-test")!!.getBoolean("tombstone"))
        } finally {
            store.close()
            context.deleteDatabase("vishnu-data-plane.db")
        }
    }
}