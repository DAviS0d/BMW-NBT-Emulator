package com.shilapi.xcertplay.platform

import org.slf4j.LoggerFactory

/**
 * JVM stand-in for the Android `Log` API used by the ported protocol code.
 *
 * Keeps the ported sources byte-compatible with their original call sites while routing
 * everything through slf4j.
 */
object Log {
    private val loggers = java.util.concurrent.ConcurrentHashMap<String, org.slf4j.Logger>()

    private fun logger(tag: String): org.slf4j.Logger = loggers.computeIfAbsent(tag) {
        LoggerFactory.getLogger(it)
    }

    @JvmStatic
    fun d(tag: String, message: String): Int {
        logger(tag).debug(message)
        return 0
    }

    @JvmStatic
    fun i(tag: String, message: String): Int {
        logger(tag).info(message)
        return 0
    }

    @JvmStatic
    fun w(tag: String, message: String): Int {
        logger(tag).warn(message)
        return 0
    }

    @JvmStatic
    fun w(tag: String, message: String, error: Throwable?): Int {
        logger(tag).warn(message, error)
        return 0
    }

    @JvmStatic
    fun e(tag: String, message: String): Int {
        logger(tag).error(message)
        return 0
    }

    @JvmStatic
    fun e(tag: String, message: String, error: Throwable?): Int {
        logger(tag).error(message, error)
        return 0
    }

    @JvmStatic
    fun isLoggable(tag: String, level: Int): Boolean = logger(tag).isDebugEnabled || true
}
