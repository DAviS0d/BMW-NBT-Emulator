package com.shilapi.xcertplay.mfi

enum class MfiCertificateType {
    MFI,
    BAA,
}

class BaaCertificatePair(leaf: ByteArray, intermediate: ByteArray) {
    val leaf: ByteArray = leaf.copyOf()
    val intermediate: ByteArray = intermediate.copyOf()

    init {
        require(this.leaf.isNotEmpty()) { "BAA leaf certificate must not be empty" }
        require(this.intermediate.isNotEmpty()) { "BAA intermediate certificate must not be empty" }
    }
}

/** Common certificate/signing contract implemented by local key material and remote services. */
interface MfiAuthenticator {
    val certificateType: MfiCertificateType
        get() = MfiCertificateType.MFI

    fun protocolMajor(): Int

    fun readCertificate(
        maximumOutputLength: Int = DEFAULT_MAXIMUM_CERTIFICATE_OUTPUT_LENGTH,
    ): ByteArray

    fun signChallenge(challenge: ByteArray): ByteArray

    fun baaCertificates(): BaaCertificatePair =
        throw MfiInvalidDataException("Authenticator does not provide BAA certificates")

    companion object {
        const val DEFAULT_MAXIMUM_CERTIFICATE_OUTPUT_LENGTH = 65_525
    }
}

/** MFi-layer failures. */
sealed class MfiException(message: String, cause: Throwable? = null) : Exception(message, cause)

class MfiInvalidDataException(message: String, cause: Throwable? = null) : MfiException(message, cause)

/** The authentication request did not complete; [errorCode] is best-effort only. */
class MfiAuthenticationFailedException(val errorCode: Int?, cause: Throwable? = null) :
    MfiException(
        if (errorCode == null) "MFi authentication failed (error code unavailable)"
        else "MFi authentication failed with error 0x${errorCode.toString(16)}",
        cause,
    )
