package ai.personal.companion

import android.net.Uri


data class PairingPayload(
    val version: Int,
    val token: String,
    val code: String,
    val expiresAtMillis: Long,
    val baseUrl: String? = null,
    val serviceId: String? = null,
    val certSha256: String? = null,
    val fallbackUrl: String? = null,
) {
    val zeroConfig: Boolean get() = version == 2 && !serviceId.isNullOrBlank() && !certSha256.isNullOrBlank()
}

object PairingPayloadParser {
    private const val SCHEME = "vishnu"
    private const val HOST = "pair"
    private val V1_FIELDS = setOf("v", "base", "token", "code", "expires")
    private val V2_REQUIRED = setOf("v", "service", "fp", "token", "code", "expires")
    private val V2_FIELDS = V2_REQUIRED + "fallback"
    private val LOCAL_HOSTS = setOf("127.0.0.1", "localhost", "::1")
    private val SERVICE = Regex("^[A-Za-z0-9_-]{8,64}$")
    private val FINGERPRINT = Regex("^[0-9a-fA-F]{64}$")

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
        val version = uri.getQueryParameter("v")?.toIntOrNull()
            ?: throw IllegalArgumentException("Unsupported Vishnu pairing QR version")
        val fields = uri.queryParameterNames
        val allowed = if (version == 1) V1_FIELDS else if (version == 2) V2_FIELDS else emptySet()
        val required = if (version == 1) V1_FIELDS else if (version == 2) V2_REQUIRED else emptySet()
        if (allowed.isEmpty() || !fields.containsAll(required) || !allowed.containsAll(fields)) {
            throw IllegalArgumentException("Pairing QR code fields are invalid")
        }
        for (field in fields) {
            if (uri.getQueryParameters(field).size != 1) {
                throw IllegalArgumentException("Pairing QR code fields are invalid")
            }
        }
        val token = uri.getQueryParameter("token").orEmpty().trim()
        val code = uri.getQueryParameter("code").orEmpty().trim()
        if (token.length !in 16..256) throw IllegalArgumentException("Pairing token length is invalid")
        if (code.length != 6 || code.any { !it.isDigit() }) throw IllegalArgumentException("Pairing code must contain exactly six digits")
        val expiresSeconds = uri.getQueryParameter("expires")?.toDoubleOrNull()
            ?: throw IllegalArgumentException("Pairing expiry is invalid")
        val expiresMillis = (expiresSeconds * 1000.0).toLong()
        if (expiresMillis <= nowMillis) throw IllegalArgumentException("This pairing QR code has expired")
        if (version == 1) {
            val base = normalizeOrigin(uri.getQueryParameter("base").orEmpty(), allowLocalHttp)
            return PairingPayload(version, token, code, expiresMillis, baseUrl = base)
        }
        val service = uri.getQueryParameter("service").orEmpty().trim()
        val fingerprint = uri.getQueryParameter("fp").orEmpty().trim().lowercase()
        if (!SERVICE.matches(service)) throw IllegalArgumentException("Local Vishnu service identity is invalid")
        if (!FINGERPRINT.matches(fingerprint)) throw IllegalArgumentException("Local Vishnu TLS fingerprint is invalid")
        val fallbackRaw = uri.getQueryParameter("fallback")?.trim().orEmpty()
        val fallback = if (fallbackRaw.isBlank()) null else normalizeOrigin(fallbackRaw, false)
        return PairingPayload(
            version = 2,
            token = token,
            code = code,
            expiresAtMillis = expiresMillis,
            serviceId = service,
            certSha256 = fingerprint,
            fallbackUrl = fallback,
        )
    }
}