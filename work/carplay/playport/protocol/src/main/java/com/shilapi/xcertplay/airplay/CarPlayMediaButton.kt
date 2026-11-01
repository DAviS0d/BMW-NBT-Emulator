package com.shilapi.xcertplay.airplay

/**
 * Media keys → CarPlay media HID presses (indices into [AirPlayHid]'s media report).
 *
 * The numeric key codes are the Android `KeyEvent` values emitted by head-unit firmwares; they are
 * kept verbatim so browser clients and future hardware integrations share one mapping.
 */
object CarPlayMediaButton {
    const val PLAY = 1
    const val PAUSE = 2
    const val PLAY_PAUSE = 3
    const val NEXT = 4
    const val PREVIOUS = 5

    const val KEYCODE_HEADSETHOOK = 79
    const val KEYCODE_MEDIA_PLAY_PAUSE = 85
    const val KEYCODE_MEDIA_NEXT = 87
    const val KEYCODE_MEDIA_PREVIOUS = 88
    const val KEYCODE_MEDIA_PLAY = 126
    const val KEYCODE_MEDIA_PAUSE = 127
    const val KEYCODE_VOICE_ASSIST = 231

    /** BYD's steering-wheel play/pause key; the firmware normally rewrites it to MEDIA_PLAY/PAUSE. */
    const val KEYCODE_BYD_AUTO_MEDIA_PLAY_PAUSE = 353

    /** BYD's steering-wheel voice key: a short press, and the code the wheel sends for a long press. */
    const val KEYCODE_BYD_AUTO_MEDIA_VOICE = 304
    const val KEYCODE_BYD_AUTO_MEDIA_VOICE_LONG = 312

    /**
     * Whether [keyCode] is a voice key that opens Siri. A wheel may send each press as an instant
     * down/up pair, so a long press can arrive as its own key rather than as a held one.
     */
    fun opensSiri(keyCode: Int): Boolean = keyCode == KEYCODE_VOICE_ASSIST ||
        keyCode == KEYCODE_BYD_AUTO_MEDIA_VOICE || keyCode == KEYCODE_BYD_AUTO_MEDIA_VOICE_LONG

    /** The CarPlay press for [keyCode], or null when the key is not a media key CarPlay handles. */
    fun forKeyCode(keyCode: Int): Int? = when (keyCode) {
        KEYCODE_MEDIA_NEXT -> NEXT
        KEYCODE_MEDIA_PREVIOUS -> PREVIOUS
        KEYCODE_MEDIA_PLAY,
        KEYCODE_MEDIA_PAUSE,
        KEYCODE_MEDIA_PLAY_PAUSE,
        KEYCODE_HEADSETHOOK,
        KEYCODE_BYD_AUTO_MEDIA_PLAY_PAUSE -> PLAY_PAUSE
        else -> null
    }
}
