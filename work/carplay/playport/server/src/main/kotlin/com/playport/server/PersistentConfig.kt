package com.playport.server

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.attribute.PosixFilePermission
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class DisplayPrefs(
    val width: Int = 1280,
    val height: Int = 720,
    val fps: Int = 60,
    val uiScale: Int = 100,
    val hevc: Boolean = false,
)

/** Settings persisted between runs in `~/.playport/config.json`. */
@Serializable
data class PersistentConfig(
    val deviceName: String = "PlayPort",
    val model: String = "playport",
    val manufacturer: String = "playport",
    val airPlayPort: Int = 7000,
    val httpPort: Int = 8080,
    val display: DisplayPrefs = DisplayPrefs(),
    val wireless: Boolean = false,
    val wifiSsid: String? = null,
    val wifiPassphrase: String? = null,
    val wifiChannel: Int = 0,
    val wifiSecurity: String = "wpa2",
    val bluetoothDeviceAddress: String? = null,
    val mdns: String = "auto",
) {
    /** Server defaults from this file (CLI flags are applied on top and override). */
    fun toServerDefaults(identityDir: Path, stateDir: Path): ServerConfig = ServerConfig(
        deviceName = deviceName,
        model = model,
        manufacturer = manufacturer,
        airPlayPort = airPlayPort,
        httpPort = httpPort,
        displayWidth = display.width,
        displayHeight = display.height,
        displayFps = display.fps,
        uiScale = display.uiScale,
        hevc = display.hevc,
        wireless = wireless,
        wifiSsid = wifiSsid,
        wifiPassphrase = wifiPassphrase,
        wifiChannel = wifiChannel,
        wifiSecurity = when (wifiSecurity.lowercase()) {
            "open" -> com.shilapi.xcertplay.transport.Iap2WirelessSecurity.NONE
            "wpa3" -> com.shilapi.xcertplay.transport.Iap2WirelessSecurity.WPA3_ONLY
            else -> com.shilapi.xcertplay.transport.Iap2WirelessSecurity.WPA_WPA2
        },
        bluetoothDeviceAddress = bluetoothDeviceAddress,
        mdns = mdns,
        identityDir = identityDir,
        stateDir = stateDir,
    )

    companion object {
        fun of(config: ServerConfig, display: DisplayState): PersistentConfig = PersistentConfig(
            deviceName = config.deviceName,
            model = config.model,
            manufacturer = config.manufacturer,
            airPlayPort = config.airPlayPort,
            httpPort = config.httpPort,
            display = DisplayPrefs(
                width = display.width,
                height = display.height,
                fps = display.fps,
                uiScale = display.uiScale,
                hevc = display.hevc,
            ),
            wireless = config.wireless,
            wifiSsid = config.wifiSsid,
            wifiPassphrase = config.wifiPassphrase,
            wifiChannel = config.wifiChannel,
            wifiSecurity = when (config.wifiSecurity) {
                com.shilapi.xcertplay.transport.Iap2WirelessSecurity.NONE -> "open"
                com.shilapi.xcertplay.transport.Iap2WirelessSecurity.WPA3_ONLY -> "wpa3"
                else -> "wpa2"
            },
            bluetoothDeviceAddress = config.bluetoothDeviceAddress,
            mdns = config.mdns,
        )
    }
}

/** Reads and writes [PersistentConfig] under the state directory. */
class ConfigStore(private val stateDir: Path) {
    private val file: Path get() = stateDir.resolve(FILE_NAME)
    private val json = Json { prettyPrint = true; encodeDefaults = true }

    fun load(): PersistentConfig? {
        if (!Files.isRegularFile(file)) return null
        return runCatching {
            json.decodeFromString(PersistentConfig.serializer(), Files.readString(file))
        }.getOrNull()
    }

    fun save(config: PersistentConfig) {
        runCatching {
            Files.createDirectories(stateDir)
            val temporary = stateDir.resolve("$FILE_NAME.tmp")
            Files.writeString(temporary, json.encodeToString(PersistentConfig.serializer(), config))
            restrictToOwner(temporary)
            Files.move(temporary, file, StandardCopyOption.REPLACE_EXISTING)
        }
    }

    private fun restrictToOwner(path: Path) {
        try {
            Files.setPosixFilePermissions(
                path,
                setOf(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE),
            )
        } catch (_: UnsupportedOperationException) {
            // Non-POSIX filesystems keep default permissions.
        }
    }

    private companion object {
        const val FILE_NAME = "config.json"
    }
}
