package com.playport.server

import com.shilapi.xcertplay.airplay.MicrophoneConfig
import com.shilapi.xcertplay.airplay.MicrophoneCounters
import com.shilapi.xcertplay.airplay.MicrophonePacketizer
import java.io.Closeable
import java.net.DatagramPacket
import java.net.DatagramSocket
import org.slf4j.LoggerFactory

/**
 * Sends captured microphone audio to the phone on the CarPlay input stream the phone advertised
 * (speech recognition for Siri, telephony for calls).
 */
class MicUplink(private val config: MicrophoneConfig) : Closeable {
    private val log = LoggerFactory.getLogger("mic")
    private val socket = DatagramSocket()
    private val counters = MicrophoneCounters()

    val audioType: String get() = config.audioType
    val sampleRate: Int get() = config.sampleRate
    val channels: Int get() = config.channels
    val samplesPerPacket: Int get() = config.samplesPerPacket
    val codec: String get() = config.codec.name.lowercase()
    val bitrate: Int? get() = config.bitrate

    fun send(payload: ByteArray, samples: Int) {
        if (payload.isEmpty()) return
        try {
            val packet = MicrophonePacketizer.sealPacket(
                key = config.key,
                payloadType = config.payloadType,
                counters = counters,
                body = payload,
                samples = samples,
            )
            socket.send(DatagramPacket(packet, packet.size, config.host, config.port))
        } catch (error: Exception) {
            log.warn("microphone packet send failed: {}", error.message)
        }
    }

    override fun close() {
        runCatching { socket.close() }
    }
}
