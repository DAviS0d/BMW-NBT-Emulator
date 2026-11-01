package com.playport.server

import com.shilapi.xcertplay.airplay.AirPlayIcon
import java.awt.Color
import java.awt.RenderingHints
import java.awt.image.BufferedImage
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.nio.file.Path
import javax.imageio.ImageIO
import org.slf4j.LoggerFactory

/** Supplies a square PNG to the phone's native manufacturer button. */
object OemIcon {
    fun load(path: Path): List<AirPlayIcon> {
        if (!Files.isRegularFile(path)) return emptyList()
        return try {
            val source = ImageIO.read(path.toFile()) ?: return emptyList()
            val size = 256
            val image = BufferedImage(size, size, BufferedImage.TYPE_INT_ARGB)
            val graphics = image.createGraphics()
            try {
                graphics.color = Color(source.getRGB(0, 0), true)
                graphics.fillRect(0, 0, size, size)
                graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BICUBIC)
                val scale = minOf(size.toDouble() / source.width, size.toDouble() / source.height)
                val width = (source.width * scale).toInt().coerceAtLeast(1)
                val height = (source.height * scale).toInt().coerceAtLeast(1)
                graphics.drawImage(source, (size - width) / 2, (size - height) / 2, width, height, null)
            } finally { graphics.dispose() }
            val encoded = ByteArrayOutputStream()
            check(ImageIO.write(image, "png", encoded))
            listOf(AirPlayIcon(size, size, encoded.toByteArray()))
        } catch (error: Exception) {
            LoggerFactory.getLogger("oem-icon").warn("Could not load {}: {}", path, error.message)
            emptyList()
        }
    }
}
