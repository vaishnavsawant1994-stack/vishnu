package ai.personal.companion

import okhttp3.OkHttpClient
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

object PinnedTls {
    fun normalizeFingerprint(value: String?): String? {
        val clean = value?.trim()?.lowercase().orEmpty()
        return clean.takeIf { it.matches(Regex("^[0-9a-f]{64}$")) }
    }

    fun certificateFingerprint(certificate: X509Certificate): String =
        MessageDigest.getInstance("SHA-256").digest(certificate.encoded).joinToString("") { "%02x".format(it) }

    fun client(expectedFingerprint: String?): OkHttpClient {
        val pin = normalizeFingerprint(expectedFingerprint)
            ?: return OkHttpClient.Builder()
                .callTimeout(15, TimeUnit.SECONDS)
                .retryOnConnectionFailure(false)
                .followRedirects(false)
                .followSslRedirects(false)
                .build()
        val trust = object : X509TrustManager {
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) = Unit
            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                val leaf = chain?.firstOrNull() ?: throw CertificateException("Vishnu did not present a certificate")
                if (!MessageDigest.isEqual(
                        certificateFingerprint(leaf).toByteArray(Charsets.US_ASCII),
                        pin.toByteArray(Charsets.US_ASCII),
                    )) {
                    throw CertificateException("Vishnu TLS identity does not match the pairing QR")
                }
            }
        }
        val context = SSLContext.getInstance("TLS")
        context.init(null, arrayOf(trust), SecureRandom())
        return OkHttpClient.Builder()
            .sslSocketFactory(context.socketFactory, trust)
            .hostnameVerifier { _, session ->
                val leaf = session.peerCertificates.firstOrNull() as? X509Certificate
                leaf != null && certificateFingerprint(leaf) == pin
            }
            .callTimeout(15, TimeUnit.SECONDS)
            .retryOnConnectionFailure(false)
            .followRedirects(false)
            .followSslRedirects(false)
            .build()
    }
}