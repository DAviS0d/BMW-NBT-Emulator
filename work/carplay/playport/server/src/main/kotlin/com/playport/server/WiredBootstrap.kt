package com.playport.server

import com.shilapi.xcertplay.iap2.session.Iap2Session
import com.shilapi.xcertplay.mfi.Iap2MfiAuthenticationClient
import com.shilapi.xcertplay.transport.Iap2IdentificationConfig
import com.shilapi.xcertplay.transport.Iap2WiredCarPlayEndpoint
import com.shilapi.xcertplay.transport.Iap2WiredControlClient
import java.io.Closeable
import java.net.Inet6Address
import java.nio.file.Files
import org.slf4j.LoggerFactory

/** Wired iAP2 over Apple's USB service. The USB network adapter is owned by Windows. */
class WiredBootstrap(private val server: CarPlayServer) : Closeable {
    private val log = LoggerFactory.getLogger("wired")
    @Volatile private var stopped = false
    @Volatile private var stream: ProcessByteStream? = null

    fun start() {
        require(server.bindAddress is Inet6Address) {
            "Wired CarPlay requires --bind with the USB NCM adapter's IPv6 address and scope"
        }
        require(Files.isRegularFile(server.config.usbHelper)) { "USB carkit helper not found: ${server.config.usbHelper}" }
        Thread(::run, "wired-bootstrap").apply { isDaemon = true; start() }
    }

    private fun run() {
        while (!stopped) {
            try {
                val config = server.config
                val command = mutableListOf(config.usbPython)
                if (config.usbPython.equals("py", ignoreCase = true) || config.usbPython.equals("py.exe", ignoreCase = true)) command.add("-3.12")
                command.addAll(listOf(config.usbHelper.toAbsolutePath().toString(), "--carkit"))
                val pipe = ProcessByteStream(ProcessBuilder(command).start(), "usb-carkit").also { stream = it }
                pipe.use {
                    Iap2Session.open(pipe, traceContext = "wired-usb", onTrace = { log.debug(it) }).use { session ->
                        log.info("USB carkit open; starting wired iAP2 identification")
                        val result = Iap2WiredControlClient(session, Iap2MfiAuthenticationClient(server.mfi)).run(
                            identification = Iap2IdentificationConfig(
                                name = config.deviceName,
                                modelIdentifier = config.model,
                                manufacturer = config.manufacturer,
                                serialNumber = "MIB2USB-" + server.deviceId.replace(":", ""),
                                firmwareVersion = "1.0.0", hardwareVersion = "1.0",
                                carPlayUsbInterfaceNumber = 1,
                            ),
                            endpoint = Iap2WiredCarPlayEndpoint(
                                ipv6Addresses = listOf(server.bindAddress.hostAddress.substringBefore('%')),
                                airPlayPort = config.airPlayPort,
                                publicKey = server.identity.publicKeyHex,
                                sourceVersion = config.sourceVersion,
                                deviceIdentifier = server.deviceId,
                            ),
                            availableCurrentMilliAmps = 500,
                            timeoutMillis = Iap2WiredControlClient.NO_TIMEOUT_MILLIS,
                            onProgress = { log.info(it) },
                        )
                        log.info("Wired control ended stage={} reason={}", result.stage, result.terminal)
                    }
                }
            } catch (error: Exception) {
                if (!stopped) log.warn("Wired USB bootstrap: {}", error.message)
            } finally {
                runCatching { stream?.close() }
                stream = null
            }
            if (!stopped) try { Thread.sleep(3000) } catch (_: InterruptedException) { return }
        }
    }

    override fun close() {
        stopped = true
        stream?.close()
        stream = null
    }

    fun reconnect() {
        if (!stopped) stream?.close()
    }
}
