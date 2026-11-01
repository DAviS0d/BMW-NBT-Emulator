package com.playport.server

import com.shilapi.xcertplay.airplay.AirPlayConfig
import com.shilapi.xcertplay.airplay.AirPlayIdentity
import com.shilapi.xcertplay.network.CarPlayBonjourProtocol
import java.io.Closeable
import java.net.InetAddress
import javax.jmdns.JmDNS
import javax.jmdns.ServiceInfo
import org.slf4j.LoggerFactory

/**
 * Publishes the AirPlay service so the iPhone discovers this server as a CarPlay accessory.
 *
 * Uses the same TXT records as the Android head-unit implementation.
 */
class JmDnsAdvertiser(
    private val config: AirPlayConfig,
    private val identity: AirPlayIdentity,
    private val address: InetAddress,
) : ServiceAdvertiser {
    private val log = LoggerFactory.getLogger("mdns")
    @Volatile private var dns: JmDNS? = null
    @Volatile private var serviceInfo: ServiceInfo? = null

    override fun start() {
        val hostLabel = "playport-${config.deviceId.replace(":", "").takeLast(8).lowercase()}"
        val instance = JmDNS.create(address, hostLabel)
        dns = instance
        val txt = CarPlayBonjourProtocol.airPlayTxtRecords(config, identity)
        val info = ServiceInfo.create(
            "${CarPlayBonjourProtocol.AIRPLAY_SERVICE_TYPE}.local.",
            config.deviceName,
            config.port,
            0,
            0,
            txt,
        )
        serviceInfo = info
        instance.registerService(info)
        log.info(
            "mDNS advertised {} on {}:{} records={}",
            config.deviceName,
            address.hostAddress,
            config.port,
            txt.keys.sorted().joinToString(","),
        )
    }

    override fun close() {
        val info = serviceInfo
        val instance = dns
        serviceInfo = null
        dns = null
        runCatching { info?.let { instance?.unregisterService(it) } }
        runCatching { instance?.close() }
    }
}
