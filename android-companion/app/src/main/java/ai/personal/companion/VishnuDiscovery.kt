package ai.personal.companion

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import java.util.concurrent.atomic.AtomicBoolean

object VishnuDiscovery {
    private const val SERVICE_TYPE = "_vishnu._tcp."

    fun discover(
        context: Context,
        serviceId: String,
        timeoutMillis: Long = 8_000,
        completion: (Result<String>) -> Unit,
    ) {
        val manager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
        val expectedName = "Vishnu-$serviceId"
        val finished = AtomicBoolean(false)
        lateinit var listener: NsdManager.DiscoveryListener

        fun finish(result: Result<String>) {
            if (!finished.compareAndSet(false, true)) return
            try { manager.stopServiceDiscovery(listener) } catch (_: Exception) {}
            completion(result)
        }

        listener = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) = Unit
            override fun onDiscoveryStopped(serviceType: String) = Unit
            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                finish(Result.failure(IllegalStateException("Vishnu discovery could not start ($errorCode)")))
            }
            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) = Unit
            override fun onServiceLost(serviceInfo: NsdServiceInfo) = Unit
            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                if (serviceInfo.serviceName != expectedName) return
                manager.resolveService(serviceInfo, object : NsdManager.ResolveListener {
                    override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                        finish(Result.failure(IllegalStateException("Vishnu was found but could not be resolved ($errorCode)")))
                    }
                    override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                        val rawHost = serviceInfo.host?.hostAddress.orEmpty()
                        val port = serviceInfo.port
                        if (rawHost.isBlank() || port !in 1..65535) {
                            finish(Result.failure(IllegalStateException("Vishnu discovery returned an invalid endpoint")))
                            return
                        }
                        val host = if (rawHost.contains(':') && !rawHost.startsWith("[")) "[$rawHost]" else rawHost
                        finish(Result.success("https://$host:$port"))
                    }
                })
            }
        }
        manager.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, listener)
        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
            finish(Result.failure(IllegalStateException("Could not find this Vishnu on the local network")))
        }, timeoutMillis.coerceIn(1_000, 30_000))
    }
}