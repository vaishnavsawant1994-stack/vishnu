package ai.personal.companion

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
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
    }

    @Test
    fun pairingQrParsesAndNormalizesOrigin() {
        val token = "a".repeat(32)
        val raw = "vishnu://pair?v=1&base=https%3A%2F%2Fvishnu.example.test%2Fignored&token=$token&code=123456&expires=9999999999"
        val payload = PairingPayloadParser.parse(raw, nowMillis = 100_000)
        assertEquals("https://vishnu.example.test", payload.baseUrl)
        assertEquals(token, payload.token)
        assertEquals("123456", payload.code)
    }

    @Test
    fun pairingQrRejectsExpiredOfferAndRemoteHttp() {
        val token = "a".repeat(32)
        val expired = "vishnu://pair?v=1&base=https%3A%2F%2Fvishnu.example.test&token=$token&code=123456&expires=100"
        assertThrows(IllegalArgumentException::class.java) {
            PairingPayloadParser.parse(expired, nowMillis = 101_000)
        }
        assertThrows(IllegalArgumentException::class.java) {
            PairingPayloadParser.normalizeOrigin("http://vishnu.example.test")
        }
        assertEquals(
            "http://localhost:8766",
            PairingPayloadParser.normalizeOrigin("http://localhost:8766/path", allowLocalHttp = true),
        )
    }
}
