package ai.personal.companion

import android.net.Uri


data class PairingPayload(
    val baseUrl: String,
    val token: String,
    val code: String,
    val expiresAtMillis: Long,
)

object PairingPayloadParser {
    private const val SCHEME = "vishnu"
    private const val HOST = "pair"
    private const val VERSION = "1"
    private val FIELDS = setOf("v", "base", "token", "code", "expires")
    private val LOCAL_HOSTS = setOf("127.0.0.1", "localhost", "::1")

    fun normalizeOrigin(raw: String, allowLocalHttp: Boolean = false): String {
        val uri = Uri.parse(raw.trim())
        val scheme = uri.scheme?.lowercase() ?: throw IllegalArgumentException("Vishnu URL must include a scheme")
        val host = uri.host ?: throw IllegalArgumentException("Vishnu URL must include a hostname")
        if (!uri.userInfo.isNullOrBlank() || (uri.encodedAuthority?.contains('@') == true)) {
            throw IllegalArgumentException("Do not embed credentials in the Vishnu URL")
        }
        if (!uri.fragment.isNullOrBlank()) {
            throw IllegalArgumentException("Vishnu URL must not contain a fragment")
        }
        val localHttp = scheme == "http" && allowLocalHttp && host.lowercase() in LOCAL_HOSTS
        if (scheme != "https" && !localHttp) {
            throw IllegalArgumentException("Use HTTPS. Plain HTTP is allowed only for explicitly enabled localhost development")
        }
        val hostPart = if (host.contains(':') && !host.startsWith("[")) "[$host]" else host
        val portPart = if (uri.port >= 0) ":${uri.port}" else ""
        return "$scheme://$hostPart$portPart"
    }

    fun parse(raw: String, allowLocalHttp: Boolean = false, nowMillis: Long = System.currentTimeMillis()): PairingPayload {
        val uri = Uri.parse(raw.trim())
        if (uri.scheme != SCHEME || uri.host != HOST || (uri.path.orEmpty() !in setOf("", "/"))) {
            throw IllegalArgumentException("This is not a Vishnu pairing QR code")
        }
        if (!uri.fragment.isNullOrBlank()) {
            throw IllegalArgumentException("Pairing QR code must not contain a fragment")
        }
        if (uri.queryParameterNames != FIELDS) {
            throw IllegalArgumentException("Pairing QR code fields are invalid")
        }
        for (field in FIELDS) {
            if (uri.getQueryParameters(field).size != 1) {
                throw IllegalArgumentException("Pairing QR code fields are invalid")
            }
        }
        if (uri.getQueryParameter("v") != VERSION) {
            throw IllegalArgumentException("Unsupported Vishnu pairing QR version")
        }
        val base = normalizeOrigin(uri.getQueryParameter("base").orEmpty(), allowLocalHttp)
        val token = uri.getQueryParameter("token").orEmpty().trim()
        val code = uri.getQueryParameter("code").orEmpty().trim()
        if (token.length !in 16..256) {
            throw IllegalArgumentException("Pairing token length is invalid")
        }
        if (code.length != 6 || code.any { !it.isDigit() }) {
            throw IllegalArgumentException("Pairing code must contain exactly six digits")
        }
        val expiresSeconds = uri.getQueryParameter("expires")?.toDoubleOrNull()
            ?: throw IllegalArgumentException("Pairing expiry is invalid")
        val expiresMillis = (expiresSeconds * 1000.0).toLong()
        if (expiresMillis <= nowMillis) {
            throw IllegalArgumentException("This pairing QR code has expired")
        }
        return PairingPayload(base, token, code, expiresMillis)
    }
}
