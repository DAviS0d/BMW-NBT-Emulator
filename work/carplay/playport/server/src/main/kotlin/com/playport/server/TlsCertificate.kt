package com.playport.server

import java.math.BigInteger
import java.net.InetAddress
import java.nio.file.Files
import java.nio.file.Path
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.Security
import java.util.Date
import org.bouncycastle.asn1.x500.X500Name
import org.bouncycastle.asn1.x509.Extension
import org.bouncycastle.asn1.x509.GeneralName
import org.bouncycastle.asn1.x509.GeneralNames
import org.bouncycastle.cert.jcajce.JcaX509CertificateConverter
import org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder
import org.bouncycastle.jce.provider.BouncyCastleProvider
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder

/**
 * Self-signed TLS material for the browser UI.
 *
 * WebCodecs (used for video/audio decoding) is only exposed in secure contexts, so the UI must be
 * served over HTTPS when it is opened from anything other than localhost. The certificate is
 * self-signed: browsers show a one-time warning to click through.
 */
object TlsCertificate {
    private const val ALIAS = "playport"
    private const val FILE_NAME = "tls-keystore.p12"
    private val PASSWORD = "playport".toCharArray()

    data class Material(val keyStore: KeyStore, val alias: String, val password: CharArray)

    fun loadOrCreate(stateDir: Path, addresses: List<InetAddress>): Material {
        val file = stateDir.resolve(FILE_NAME)
        if (Files.isRegularFile(file)) {
            val existing = runCatching {
                val keyStore = KeyStore.getInstance("PKCS12")
                Files.newInputStream(file).use { keyStore.load(it, PASSWORD) }
                if (keyStore.containsAlias(ALIAS)) Material(keyStore, ALIAS, PASSWORD) else null
            }.getOrNull()
            if (existing != null) return existing
        }
        return generate(file, addresses)
    }

    private fun generate(file: Path, addresses: List<InetAddress>): Material {
        Security.addProvider(BouncyCastleProvider())
        val keyPair = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
        val now = System.currentTimeMillis()
        val subject = X500Name("CN=playport")
        val builder = JcaX509v3CertificateBuilder(
            subject,
            BigInteger.valueOf(now),
            Date(now - 24L * 60 * 60 * 1000),
            Date(now + 3650L * 24 * 60 * 60 * 1000),
            subject,
            keyPair.public,
        )
        val names = mutableListOf(
            GeneralName(GeneralName.dNSName, "localhost"),
            GeneralName(GeneralName.dNSName, "playport"),
        )
        addresses.distinctBy { it.hostAddress }.forEach {
            names.add(GeneralName(GeneralName.iPAddress, it.hostAddress))
        }
        builder.addExtension(Extension.subjectAlternativeName, false, GeneralNames(names.toTypedArray()))
        val signer = JcaContentSignerBuilder("SHA256withRSA").build(keyPair.private)
        val certificate = JcaX509CertificateConverter().getCertificate(builder.build(signer))

        val keyStore = KeyStore.getInstance("PKCS12")
        keyStore.load(null, null)
        keyStore.setKeyEntry(ALIAS, keyPair.private, PASSWORD, arrayOf(certificate))
        Files.createDirectories(file.parent)
        Files.newOutputStream(file).use { keyStore.store(it, PASSWORD) }
        return Material(keyStore, ALIAS, PASSWORD)
    }
}
