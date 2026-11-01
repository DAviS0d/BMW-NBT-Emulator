package com.playport.server

import io.ktor.server.testing.testApplication
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.client.statement.bodyAsBytes
import io.ktor.http.HttpStatusCode
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.nio.file.Path
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.junit.Assert.*
import org.junit.Test

class MibBridgeTest {
    @Test fun frameAccessRequiresTokenAndLiveSessionAndExpires() = testApplication {
        val config = ServerConfig(identityDir = Path.of("identity"), stateDir = Path.of("state"), accessToken = "test-token")
        val hub = WebHub(config, DisplayState(800, 480, 30, 100))
        application { hub.install(this, Path.of("missing-web-root")) }
        val path = "/api/mib-frame?token=test-token"
        val jpeg = byteArrayOf(0xff.toByte(), 0xd8.toByte(), 0xff.toByte(), 0xd9.toByte())
        assertEquals(HttpStatusCode.Forbidden, client.get("/api/mib-frame").status)
        assertEquals(HttpStatusCode.Forbidden, client.post("/api/mib-frame") { setBody(jpeg) }.status)
        assertEquals(HttpStatusCode.BadRequest, client.post(path) { setBody(byteArrayOf(1, 2, 3, 4)) }.status)
        assertEquals("""{"audio":false,"volume":0.0}""", client.post(path) { setBody(jpeg) }.bodyAsText())
        assertEquals(HttpStatusCode.ServiceUnavailable, client.get(path).status)
        hub.setSessionState(true, "test iPhone")
        assertArrayEquals(jpeg, client.get("$path&audio=true&volume=0.23").bodyAsBytes())
        assertEquals("""{"audio":true,"volume":0.23}""", client.post(path) { setBody(jpeg) }.bodyAsText())
        client.get(path) // A screenshot must not mute or change volume.
        assertEquals("""{"audio":true,"volume":0.23}""", client.post(path) { setBody(jpeg) }.bodyAsText())
        client.get("$path&audio=true&volume=7")
        assertEquals("""{"audio":true,"volume":1.0}""", client.post(path) { setBody(jpeg) }.bodyAsText())
        client.get("$path&audio=true&volume=NaN")
        assertEquals("""{"audio":true,"volume":1.0}""", client.post(path) { setBody(jpeg) }.bodyAsText())
        client.get("$path&audio=false")
        assertEquals("""{"audio":false,"volume":0.0}""", client.post(path) { setBody(jpeg) }.bodyAsText())
        // Avoid wall-clock sleeps: make the last frame older than the two-second deadline.
        hub.javaClass.getDeclaredField("mibFrameAt").apply { isAccessible = true }.setLong(hub, System.nanoTime() - 3_000_000_000L)
        assertEquals(HttpStatusCode.ServiceUnavailable, client.get(path).status)
        hub.setSessionState(false, null)
        assertEquals(HttpStatusCode.ServiceUnavailable, client.get(path).status)
    }

    @Test fun pipeReadsPreserveByteOrderAcrossFragmentedReceivesAndEof() {
        val expected = ByteArray(20000) { (it % 251).toByte() }
        val drained = CountDownLatch(1)
        val source = object : ByteArrayInputStream(expected) {
            override fun read(b: ByteArray, off: Int, len: Int): Int = super.read(b, off, len).also {
                if (it < 0) drained.countDown()
            }
        }
        val process = object : Process() {
            override fun getInputStream() = source
            override fun getOutputStream() = ByteArrayOutputStream()
            override fun getErrorStream() = ByteArrayInputStream(byteArrayOf())
            override fun waitFor() = 0
            override fun exitValue() = 0
            override fun destroy() {}
        }
        ProcessByteStream(process, "test").use { stream ->
            assertTrue(drained.await(2, TimeUnit.SECONDS))
            val actual = ByteArrayOutputStream()
            while (true) {
                val chunk = stream.recv(31, 1000) ?: fail("pipe receive timed out").let { byteArrayOf() }
                if (chunk.isEmpty()) break
                actual.write(chunk)
            }
            assertArrayEquals(expected, actual.toByteArray())
            assertEquals(0, stream.recv(31, 0)?.size)
        }
    }
}
