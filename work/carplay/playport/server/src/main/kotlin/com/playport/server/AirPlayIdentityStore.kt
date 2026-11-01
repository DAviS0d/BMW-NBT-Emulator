package com.playport.server

import com.shilapi.xcertplay.airplay.AirPlayIdentity
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.nio.file.attribute.PosixFilePermission

/** Persists the long-term Ed25519 AirPlay identity under the state directory. */
object AirPlayIdentityStore {
    private const val FILE_NAME = "airplay-identity.properties"

    fun loadOrCreate(stateDir: Path): AirPlayIdentity {
        Files.createDirectories(stateDir)
        val file = stateDir.resolve(FILE_NAME)
        if (Files.exists(file)) {
            val properties = java.util.Properties()
            Files.newInputStream(file).use(properties::load)
            val privateKey = properties.getProperty("privateKey")?.hexToBytes()
            val publicKey = properties.getProperty("publicKey")?.hexToBytes()
            val pairingId = properties.getProperty("pairingId")
            if (privateKey != null && privateKey.size == 32 && publicKey != null && publicKey.size == 32 && !pairingId.isNullOrBlank()) {
                return AirPlayIdentity(privateKey, publicKey, pairingId)
            }
        }
        val identity = AirPlayIdentity.generate()
        val properties = java.util.Properties().apply {
            setProperty("privateKey", identity.privateKey.toHex())
            setProperty("publicKey", identity.publicKey.toHex())
            setProperty("pairingId", identity.pairingId)
        }
        val temporary = stateDir.resolve("$FILE_NAME.tmp")
        Files.newOutputStream(temporary, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING).use { output ->
            properties.store(output, "playport AirPlay identity - keep this file secret")
        }
        restrictToOwner(temporary)
        Files.move(temporary, file, StandardCopyOption.REPLACE_EXISTING)
        return identity
    }

    private fun restrictToOwner(file: Path) {
        try {
            Files.setPosixFilePermissions(
                file,
                setOf(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE),
            )
        } catch (_: UnsupportedOperationException) {
            // Non-POSIX filesystems keep default permissions.
        }
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

    private fun String.hexToBytes(): ByteArray? {
        if (length % 2 != 0) return null
        return try {
            ByteArray(length / 2) { index -> substring(index * 2, index * 2 + 2).toInt(16).toByte() }
        } catch (_: NumberFormatException) {
            null
        }
    }

    /** Stable MAC-style device id derived from the AirPlay public key. */
    fun deviceId(identity: AirPlayIdentity): String {
        val digest = java.security.MessageDigest.getInstance("SHA-256").digest(identity.publicKey)
        return "02:%02X:%02X:%02X:%02X:%02X".format(
            digest[0], digest[1], digest[2], digest[3], digest[4],
        )
    }
}
