package com.playport.server

import com.shilapi.xcertplay.airplay.AudioCodecKind
import com.shilapi.xcertplay.airplay.AudioFormat
import com.shilapi.xcertplay.airplay.VideoCodec
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Binary framing between the server and browser clients (little-endian).
 *
 * type 1 VIDEO_CONFIG:  [1][streamType u8][codec u8][width u32][height u32][avcC/hvcC record]
 * type 2 VIDEO_FRAME:   [2][streamType u8][flags u8][pts u64][Annex B NAL units]
 * type 3 AUDIO_CONFIG:  [3][streamType u8][codec u8][sampleRate u32][channels u8][nameLen u8][name][description]
 * type 4 AUDIO_PACKET:  [4][streamType u8][pts u64][one codec frame]
 * type 5 SCREEN_ACTIVE: [5][streamType u8][active u8]
 * type 6 AUDIO_STOPPED: [6][streamType u8]
 */
object Wire {
    const val VIDEO_CONFIG: Byte = 1
    const val VIDEO_FRAME: Byte = 2
    const val AUDIO_CONFIG: Byte = 3
    const val AUDIO_PACKET: Byte = 4
    const val SCREEN_ACTIVE: Byte = 5
    const val AUDIO_STOPPED: Byte = 6

    const val VIDEO_CODEC_H264: Byte = 1
    const val VIDEO_CODEC_H265: Byte = 2

    const val AUDIO_CODEC_AAC_LC: Byte = 1
    const val AUDIO_CODEC_OPUS: Byte = 2
    const val AUDIO_CODEC_LPCM: Byte = 3

    const val FLAG_KEYFRAME: Byte = 1

    fun videoCodecId(codec: VideoCodec): Byte = when (codec) {
        VideoCodec.H264 -> VIDEO_CODEC_H264
        VideoCodec.H265 -> VIDEO_CODEC_H265
    }

    fun audioCodecId(codec: AudioCodecKind): Byte = when (codec) {
        AudioCodecKind.AAC_LC -> AUDIO_CODEC_AAC_LC
        AudioCodecKind.OPUS -> AUDIO_CODEC_OPUS
        AudioCodecKind.LPCM -> AUDIO_CODEC_LPCM
    }

    fun videoConfig(
        streamType: Int,
        codec: VideoCodec,
        width: Int,
        height: Int,
        codecData: ByteArray,
    ): ByteArray {
        val buffer = ByteBuffer.allocate(12 + codecData.size).order(ByteOrder.LITTLE_ENDIAN)
        buffer.put(VIDEO_CONFIG)
        buffer.put(streamType.toByte())
        buffer.put(videoCodecId(codec))
        buffer.putInt(width)
        buffer.putInt(height)
        buffer.put(codecData)
        return buffer.array()
    }

    fun videoFrame(streamType: Int, keyframe: Boolean, naluBytes: ByteArray): ByteArray {
        val buffer = ByteBuffer.allocate(11 + naluBytes.size).order(ByteOrder.LITTLE_ENDIAN)
        buffer.put(VIDEO_FRAME)
        buffer.put(streamType.toByte())
        buffer.put(if (keyframe) FLAG_KEYFRAME else 0)
        buffer.putLong(0L)
        buffer.put(naluBytes)
        return buffer.array()
    }

    fun audioConfig(streamType: Int, format: AudioFormat): ByteArray {
        val description = when (format.codec) {
            AudioCodecKind.AAC_LC -> audioSpecificConfig(format.sampleRate, format.channels)
            else -> ByteArray(0)
        }
        val name = format.audioType.take(24).toByteArray(Charsets.UTF_8)
        val buffer = ByteBuffer.allocate(9 + name.size + description.size).order(ByteOrder.LITTLE_ENDIAN)
        buffer.put(AUDIO_CONFIG)
        buffer.put(streamType.toByte())
        buffer.put(audioCodecId(format.codec))
        buffer.putInt(format.sampleRate)
        buffer.put(format.channels.toByte())
        buffer.put(name.size.toByte())
        buffer.put(name)
        buffer.put(description)
        return buffer.array()
    }

    fun audioPacket(streamType: Int, timestampUs: Long, payload: ByteArray): ByteArray {
        val buffer = ByteBuffer.allocate(10 + payload.size).order(ByteOrder.LITTLE_ENDIAN)
        buffer.put(AUDIO_PACKET)
        buffer.put(streamType.toByte())
        buffer.putLong(timestampUs)
        buffer.put(payload)
        return buffer.array()
    }

    fun screenActive(streamType: Int, active: Boolean): ByteArray {
        return byteArrayOf(SCREEN_ACTIVE, streamType.toByte(), if (active) 1 else 0)
    }

    fun audioStopped(streamType: Int): ByteArray = byteArrayOf(AUDIO_STOPPED, streamType.toByte())

    /** MPEG-4 AudioSpecificConfig for AAC-LC: 5-bit object type, 4-bit rate index, 4-bit channels. */
    fun audioSpecificConfig(sampleRate: Int, channels: Int): ByteArray {
        val rateIndex = when (sampleRate) {
            96_000 -> 0
            88_200 -> 1
            64_000 -> 2
            48_000 -> 3
            44_100 -> 4
            32_000 -> 5
            24_000 -> 6
            22_050 -> 7
            16_000 -> 8
            12_000 -> 9
            11_025 -> 10
            8_000 -> 11
            else -> 4
        }
        val config = (2 shl 11) or (rateIndex shl 7) or (channels shl 3)
        return byteArrayOf((config ushr 8).toByte(), config.toByte())
    }

    /** True when the Annex B payload contains an H.264 IDR or H.265 IRAP picture. */
    fun isKeyFrame(annexB: ByteArray, codec: VideoCodec): Boolean {
        var index = 0
        var inspected = 0
        while (index + 4 <= annexB.size && inspected < 8) {
            val startLength = startCodeLength(annexB, index)
            if (startLength == 0) {
                index++
                continue
            }
            val nalStart = index + startLength
            if (nalStart >= annexB.size) return false
            val header = annexB[nalStart].toInt() and 0xff
            val isKey = when (codec) {
                VideoCodec.H264 -> (header and 0x1f) == 5
                VideoCodec.H265 -> ((header shr 1) and 0x3f) in 16..21
            }
            if (isKey) return true
            inspected++
            index = nalStart + 1
        }
        return false
    }

    private fun startCodeLength(bytes: ByteArray, index: Int): Int {
        if (index + 3 > bytes.size) return 0
        if (bytes[index] != 0.toByte() || bytes[index + 1] != 0.toByte()) return 0
        return when {
            index + 4 <= bytes.size && bytes[index + 2] == 0.toByte() && bytes[index + 3] == 1.toByte() -> 4
            bytes[index + 2] == 1.toByte() -> 3
            else -> 0
        }
    }

    /** Converts CarPlay's big-endian S16 PCM payload to little-endian. */
    fun byteSwapS16(payload: ByteArray): ByteArray {
        var index = 0
        while (index + 1 < payload.size) {
            val first = payload[index]
            payload[index] = payload[index + 1]
            payload[index + 1] = first
            index += 2
        }
        return payload
    }
}
