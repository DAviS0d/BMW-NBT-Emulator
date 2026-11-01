package com.playport.server

import com.shilapi.xcertplay.airplay.VideoCodec
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WireTest {
    @Test
    fun audioSpecificConfigMatchesAacLcProfiles() {
        assertArrayEquals(byteArrayOf(0x12, 0x10), Wire.audioSpecificConfig(44_100, 2))
        assertArrayEquals(byteArrayOf(0x11, 0x90.toByte()), Wire.audioSpecificConfig(48_000, 2))
        assertArrayEquals(byteArrayOf(0x11, 0x88.toByte()), Wire.audioSpecificConfig(48_000, 1))
    }

    @Test
    fun keyframeDetectionFindsH264Idr() {
        val idr = byteArrayOf(0, 0, 0, 1, 0x65, 0x11, 0x22)
        val delta = byteArrayOf(0, 0, 0, 1, 0x41, 0x11, 0x22)
        assertTrue(Wire.isKeyFrame(idr, VideoCodec.H264))
        assertFalse(Wire.isKeyFrame(delta, VideoCodec.H264))
    }

    @Test
    fun keyframeDetectionFindsH265Irap() {
        // H.265 NAL header: (type << 1); type 19 = IDR_W_RADL.
        val idr = byteArrayOf(0, 0, 0, 1, (19 shl 1).toByte(), 0x01)
        val delta = byteArrayOf(0, 0, 0, 1, (1 shl 1).toByte(), 0x01)
        assertTrue(Wire.isKeyFrame(idr, VideoCodec.H265))
        assertFalse(Wire.isKeyFrame(delta, VideoCodec.H265))
    }

    @Test
    fun byteSwapConvertsBigEndianSamples() {
        val payload = byteArrayOf(0x12, 0x34, 0xAB.toByte(), 0xCD.toByte())
        assertArrayEquals(
            byteArrayOf(0x34, 0x12, 0xCD.toByte(), 0xAB.toByte()),
            Wire.byteSwapS16(payload),
        )
    }

    @Test
    fun videoFrameHeaderCarriesFlagsAndPayload() {
        val payload = byteArrayOf(1, 2, 3)
        val frame = Wire.videoFrame(0, keyframe = true, naluBytes = payload)
        assertEquals(Wire.VIDEO_FRAME, frame[0])
        assertEquals(0.toByte(), frame[1])
        assertEquals(Wire.FLAG_KEYFRAME, frame[2])
        assertEquals(3, frame.size - 11)
        assertArrayEquals(payload, frame.copyOfRange(11, frame.size))
    }
}
