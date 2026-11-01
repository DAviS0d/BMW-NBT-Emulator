package com.shilapi.xcertplay.network

import java.net.Socket
import java.net.SocketOption
import jdk.net.ExtendedSocketOptions

/** Detect a vanished peer, without treating a legitimately idle CarPlay screen as a failure. */
internal object TcpLiveness {
    fun configure(socket: Socket, diagnostic: (String) -> Unit) {
        socket.keepAlive = true
        try {
            setIfSupported(socket, ExtendedSocketOptions.TCP_KEEPIDLE, 10)
            setIfSupported(socket, ExtendedSocketOptions.TCP_KEEPINTERVAL, 3)
            setIfSupported(socket, ExtendedSocketOptions.TCP_KEEPCOUNT, 3)
            diagnostic(
                "TCP peer health enabled idle=10s interval=3s count=3; no video-idle timeout",
            )
        } catch (failure: Exception) {
            diagnostic("TCP peer health tuning unavailable: ${failure.javaClass.simpleName}")
        }
    }

    private fun setIfSupported(socket: Socket, option: SocketOption<Int>, value: Int) {
        if (socket.supportedOptions().contains(option)) {
            socket.setOption(option, value)
        }
    }
}
