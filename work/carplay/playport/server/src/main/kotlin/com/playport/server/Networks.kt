package com.playport.server

import java.net.Inet4Address
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.SocketException

/** LAN address discovery for mDNS advertisement and the AirPlay RTSP bind. */
object Networks {
    fun detectLanAddress(): InetAddress {
        val candidates = mutableListOf<InetAddress>()
        try {
            NetworkInterface.getNetworkInterfaces().toList().forEach { iface ->
                if (!iface.isUp || iface.isLoopback || iface.isPointToPoint) return@forEach
                val name = iface.name.lowercase()
                if (name.startsWith("utun") || name.startsWith("awdl") || name.startsWith("llw") ||
                    name.startsWith("bridge") || name.startsWith("ap1")
                ) {
                    return@forEach
                }
                iface.inetAddresses.toList().forEach { address ->
                    if (address is Inet4Address && !address.isLoopbackAddress && !address.isLinkLocalAddress) {
                        candidates.add(address)
                    }
                }
            }
        } catch (error: SocketException) {
            throw IllegalStateException("No usable network interface: ${error.message}", error)
        }
        return candidates.firstOrNull() ?: InetAddress.getLoopbackAddress()
    }

    fun resolve(bindAddress: String?): InetAddress =
        if (bindAddress.isNullOrBlank()) detectLanAddress() else InetAddress.getByName(bindAddress)
}
