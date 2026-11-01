package com.shilapi.xcertplay.transport

import java.io.IOException

/**
 * Phone bring-up failures that precede iAP2 and are distinct from MFi failures.
 *
 * The name mirrors the Android origin of this code; on the desktop server the "USB" bring-up
 * paths do not exist, but the wireless bootstrap reuses the same error taxonomy.
 */
sealed class IphoneUsbException(message: String, cause: Throwable? = null) : IOException(message, cause) {
    class PermissionDenied(message: String, cause: Throwable? = null) : IphoneUsbException(message, cause)
    class DeviceUnavailable(message: String, cause: Throwable? = null) : IphoneUsbException(message, cause)
    class TimedOut(message: String, cause: Throwable? = null) : IphoneUsbException(message, cause)
    class Protocol(message: String) : IphoneUsbException(message)
}
