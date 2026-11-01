package com.playport.server

import java.nio.file.Files
import java.nio.file.Path
import java.security.Signature
import java.security.cert.CertificateFactory
import java.security.interfaces.ECPublicKey
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * Loads the recovered offline MFi identity from `../identity` and proves the key/certificate pair
 * signs correctly on the JVM — the same consistency check the CarPlay session relies on.
 */
class MfiIdentityTest {
    private val identityDir: Path = Path.of("..", "identity")

    @Test
    fun localIdentitySignsAChallengeWithTheCertificateKey() {
        val directory = identityDir.resolve("offline-mfi")
        assumeTrue("offline MFi identity not present; skipping", Files.isDirectory(directory))
        val config = ServerConfig(
            identityDir = identityDir.toAbsolutePath().normalize(),
            stateDir = Files.createTempDirectory("playport-test"),
        )
        val authenticator = MfiIdentity.load(config)
        assertTrue(authenticator.protocolMajor() == 3)

        val certificateBytes = authenticator.readCertificate()
        val certificates = CertificateFactory.getInstance("X.509")
            .generateCertificates(certificateBytes.inputStream())
        val publicKey = certificates.single().publicKey as ECPublicKey

        val challenge = ByteArray(32) { it.toByte() }
        val rawSignature = authenticator.signChallenge(challenge)
        assertTrue("expected a raw 64-byte signature", rawSignature.size == 64)

        // Re-encode the raw signature as DER and verify it with the certificate's public key.
        val verifier = Signature.getInstance("NONEwithECDSA")
        verifier.initVerify(publicKey)
        verifier.update(challenge)
        assertTrue(verifier.verify(rawToDer(rawSignature)))
    }

    @Test
    fun identityStoreRoundTripsAcrossRestarts() {
        val stateDir = Files.createTempDirectory("playport-state")
        val first = AirPlayIdentityStore.loadOrCreate(stateDir)
        val second = AirPlayIdentityStore.loadOrCreate(stateDir)
        assertArrayEquals(first.publicKey, second.publicKey)
        assertArrayEquals(first.privateKey, second.privateKey)
        assertTrue(first.pairingId == second.pairingId)
        assertTrue(AirPlayIdentityStore.deviceId(first).startsWith("02:"))
    }

    private fun rawToDer(raw: ByteArray): ByteArray {
        require(raw.size == 64)
        fun encodeInteger(bytes: ByteArray): ByteArray {
            var start = 0
            while (start < bytes.size - 1 && bytes[start] == 0.toByte()) start++
            val trimmed = bytes.copyOfRange(start, bytes.size)
            val positive = if (trimmed[0].toByte() < 0) byteArrayOf(0) + trimmed else trimmed
            return byteArrayOf(0x02, positive.size.toByte()) + positive
        }
        val r = encodeInteger(raw.copyOfRange(0, 32))
        val s = encodeInteger(raw.copyOfRange(32, 64))
        val body = r + s
        return byteArrayOf(0x30, body.size.toByte()) + body
    }
}
