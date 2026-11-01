package com.shilapi.xcertplay.airplay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CarPlayMediaButtonTest {
    @Test
    fun steeringWheelKeysMapToCarPlayMediaPresses() {
        assertEquals(CarPlayMediaButton.NEXT, CarPlayMediaButton.forKeyCode(CarPlayMediaButton.KEYCODE_MEDIA_NEXT))
        assertEquals(CarPlayMediaButton.PREVIOUS, CarPlayMediaButton.forKeyCode(CarPlayMediaButton.KEYCODE_MEDIA_PREVIOUS))
        // Head units rewrite their play/pause key into PLAY or PAUSE from the session state; both toggle.
        assertEquals(CarPlayMediaButton.PLAY_PAUSE, CarPlayMediaButton.forKeyCode(CarPlayMediaButton.KEYCODE_MEDIA_PLAY))
        assertEquals(CarPlayMediaButton.PLAY_PAUSE, CarPlayMediaButton.forKeyCode(CarPlayMediaButton.KEYCODE_MEDIA_PAUSE))
        assertEquals(CarPlayMediaButton.PLAY_PAUSE, CarPlayMediaButton.forKeyCode(CarPlayMediaButton.KEYCODE_MEDIA_PLAY_PAUSE))
        assertEquals(CarPlayMediaButton.PLAY_PAUSE, CarPlayMediaButton.forKeyCode(CarPlayMediaButton.KEYCODE_HEADSETHOOK))
        assertEquals(CarPlayMediaButton.PLAY_PAUSE, CarPlayMediaButton.forKeyCode(353))
    }

    @Test
    fun theVoiceKeyOpensSiri() {
        // Recorded on DiLink 5.0: short press 304 (scan 290), long press 312 (scan 312).
        assertTrue(CarPlayMediaButton.opensSiri(304))
        assertTrue(CarPlayMediaButton.opensSiri(312))
        assertTrue(CarPlayMediaButton.opensSiri(CarPlayMediaButton.KEYCODE_VOICE_ASSIST))
        assertFalse(CarPlayMediaButton.opensSiri(CarPlayMediaButton.KEYCODE_MEDIA_NEXT))
        assertNull(CarPlayMediaButton.forKeyCode(304))
    }

    @Test
    fun otherKeysAreLeftToTheSystem() {
        assertNull(CarPlayMediaButton.forKeyCode(24)) // KEYCODE_VOLUME_UP
        assertNull(CarPlayMediaButton.forKeyCode(86)) // KEYCODE_MEDIA_STOP
    }

    @Test
    fun indicesMatchTheAdvertisedMediaHidReport() {
        // Media report usages: 0 none, 1 play, 2 pause, 3 play/pause, 4 next, 5 previous.
        assertEquals(3, CarPlayMediaButton.PLAY_PAUSE)
        assertEquals(4, CarPlayMediaButton.NEXT)
        assertEquals(5, CarPlayMediaButton.PREVIOUS)
    }
}
