package ai.personal.companion

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.Shader
import android.view.View
import kotlin.math.cos
import kotlin.math.sin

/** Canonical native rendering of the Vishnu Intelligence Core. */
internal class VishnuGenesisCoreView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = resources.displayMetrics.density
        color = PersonalAITheme.ColorToken.brightAccent
        alpha = 105
    }

    init {
        contentDescription = "Vishnu intelligence core"
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        minimumHeight = (190 * resources.displayMetrics.density).toInt()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val cx = width / 2f
        val cy = height / 2f
        val radius = minOf(width, height) * .38f
        paint.shader = RadialGradient(cx, cy, radius,
            intArrayOf(0xFFF5FFFF.toInt(), 0xCC4DDCFF.toInt(), 0xDD031221.toInt(), 0x5520B8FF),
            floatArrayOf(0f, .08f, .70f, 1f), Shader.TileMode.CLAMP)
        canvas.drawCircle(cx, cy, radius, paint)
        paint.shader = null
        canvas.drawCircle(cx, cy, radius, line)
        for (index in 0 until 38) {
            val angle = index * 2.399
            val distance = radius * (.18f + ((index * 37) % 76) / 100f)
            val x = cx + cos(angle).toFloat() * distance
            val y = cy + sin(angle).toFloat() * distance
            if (index > 0) canvas.drawLine(x, y, cx + cos(angle + 1.8).toFloat() * distance, cy + sin(angle + 1.8).toFloat() * distance, line)
            paint.color = PersonalAITheme.ColorToken.softAccent
            paint.alpha = 225
            canvas.drawCircle(x, y, if (index % 6 == 0) 4.5f else 2.6f, paint)
        }
        canvas.save(); canvas.rotate(16f, cx, cy); canvas.drawOval(cx-radius*1.12f,cy-radius*.32f,cx+radius*1.12f,cy+radius*.32f,line); canvas.restore()
        canvas.save(); canvas.rotate(-48f, cx, cy); canvas.drawOval(cx-radius*1.06f,cy-radius*.28f,cx+radius*1.06f,cy+radius*.28f,line); canvas.restore()
    }
}
