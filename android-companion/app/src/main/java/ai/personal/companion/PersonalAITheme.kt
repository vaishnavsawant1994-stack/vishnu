package ai.personal.companion

/** Semantic companion tokens; dimensions are dp and text sizes are scaled sp. */
internal object PersonalAITheme {
    object ColorToken {
        val background = 0xFF02060B.toInt()
        val deepBackground = 0xFF030A12.toInt()
        val surface = 0xB8071522.toInt()
        val elevatedSurface = 0xFF091A28.toInt()
        val field = 0xC404101B.toInt()
        val text = 0xFFF5FAFF.toInt()
        val secondaryText = 0xFFA7BACB.toInt()
        val mutedText = 0xFF687F94.toInt()
        val accent = 0xFF20B8FF.toInt()
        val brightAccent = 0xFF4DDCFF.toInt()
        val softAccent = 0xFFA4E2FF.toInt()
        val primaryAction = 0xFF075383.toInt()
        val border = 0x4D3DAEEB.toInt()
        val danger = 0xFFFFB2B2.toInt()
    }

    object Space {
        const val x1 = 4
        const val x2 = 8
        const val x3 = 12
        const val x4 = 16
        const val x5 = 20
        const val x6 = 24
        const val x8 = 32
        const val x10 = 40
    }

    object Type {
        const val display = 36f
        const val pageTitle = 22f
        const val sectionTitle = 18f
        const val body = 16f
        const val supporting = 14f
        const val control = 14f
        const val metadata = 12f
    }

    const val controlHeightDp = 48
    const val touchTargetDp = 48
    const val cornerRadiusDp = 17
}
