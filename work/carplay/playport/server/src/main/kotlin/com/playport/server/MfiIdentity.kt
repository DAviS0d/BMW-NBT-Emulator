package com.playport.server

import com.shilapi.xcertplay.mfi.LocalMfiAuthenticationClient
import com.shilapi.xcertplay.mfi.MfiAuthenticator
import com.shilapi.xcertplay.mfi.RemoteMfiAuthenticationClient
import java.nio.file.Files

/**
 * Loads the MFi authenticator: either the local recovered identity (offline-mfi/identity.pk8 +
 * certificate.p7b) or a remote MFi server.
 *
 * The offline identity is supplied by the deployment and never committed to this repository.
 */
object MfiIdentity {
    fun load(config: ServerConfig): MfiAuthenticator {
        val remote = config.mfiRemoteServer
        if (!remote.isNullOrBlank()) {
            val client = RemoteMfiAuthenticationClient(remote, config.mfiRemoteToken)
            client.reset()
            return client
        }
        val directory = config.mfiDirectory
        require(Files.isDirectory(directory)) {
            "MFi identity directory $directory is missing; place offline-mfi/identity.pk8 and " +
                "offline-mfi/certificate.p7b there, or configure --mfi-server"
        }
        val client = LocalMfiAuthenticationClient.load(directory.toFile())
        check(client.protocolMajor() == 3) { "Expected MFi protocol major 3" }
        return client
    }
}
