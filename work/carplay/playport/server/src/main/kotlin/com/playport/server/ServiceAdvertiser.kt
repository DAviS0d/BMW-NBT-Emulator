package com.playport.server

import com.shilapi.xcertplay.airplay.AirPlayConfig
import com.shilapi.xcertplay.airplay.AirPlayIdentity
import com.shilapi.xcertplay.network.CarPlayBonjourProtocol
import java.io.Closeable
import org.slf4j.LoggerFactory

/** How the AirPlay service is published on the LAN. */
interface ServiceAdvertiser : Closeable {
    fun start()
}

/** Chooses the advertising backend: `dns-sd` on macOS (native mDNSResponder), JmDNS elsewhere. */
object Advertisers {
    private val log = LoggerFactory.getLogger("mdns")

    fun create(
        preference: String,
        config: AirPlayConfig,
        identity: AirPlayIdentity,
        address: java.net.InetAddress,
    ): ServiceAdvertiser {
        val useDnsSd = when (preference) {
            "dns-sd" -> true
            "jmdns" -> false
            else -> isMacOs() && dnsSdAvailable()
        }
        return if (useDnsSd) DnsSdAdvertiser(config, identity) else JmDnsAdvertiser(config, identity, address)
    }

    private fun isMacOs(): Boolean = System.getProperty("os.name").lowercase().contains("mac")

    private fun dnsSdAvailable(): Boolean = try {
        val process = ProcessBuilder("dns-sd", "-V").redirectErrorStream(true).start()
        process.waitFor()
        true
    } catch (_: Exception) {
        false
    }
}

/**
 * Registers the AirPlay service through macOS' system responder (`dns-sd -R`).
 *
 * The system responder is more reliable than an in-process multicast socket, especially when
 * macOS' own AirPlay Receiver is active.
 */
class DnsSdAdvertiser(
    private val config: AirPlayConfig,
    private val identity: AirPlayIdentity,
) : ServiceAdvertiser {
    private val log = LoggerFactory.getLogger("mdns")
    @Volatile private var process: Process? = null

    override fun start() {
        val txt = CarPlayBonjourProtocol.airPlayTxtRecords(config, identity)
            .map { (key, value) -> "$key=$value" }
        val command = listOf(
            "dns-sd", "-R", config.deviceName, "_airplay._tcp", ".", config.port.toString(),
        ) + txt
        val started = ProcessBuilder(command).redirectErrorStream(true).start()
        process = started
        Thread(
            {
                started.inputStream.bufferedReader().forEachLine { line ->
                    if (line.contains("Registering") || line.contains("Got a reply")) {
                        log.info("dns-sd: {}", line.trim())
                    }
                }
            },
            "dns-sd-log",
        ).apply {
            isDaemon = true
            start()
        }
        log.info(
            "system mDNS registered {} on port {} records={}",
            config.deviceName,
            config.port,
            txt.size,
        )
    }

    override fun close() {
        process?.destroy()
        process = null
    }
}
