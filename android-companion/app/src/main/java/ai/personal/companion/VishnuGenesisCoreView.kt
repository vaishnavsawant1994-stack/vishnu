package ai.personal.companion

import android.content.Context
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.view.View

/** Renders the same canonical transparent Intelligence Core used by web and iOS. */
internal class VishnuGenesisCoreView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val core = BitmapFactory.decodeResource(resources, R.drawable.vishnu_genesis_core)

    init {
        contentDescription = "Vishnu intelligence core"
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        minimumHeight = (190 * resources.displayMetrics.density).toInt()
        setLayerType(LAYER_TYPE_SOFTWARE, null)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val side = minOf(width, height).toFloat()
        val left = (width - side) / 2f
        val top = (height - side) / 2f
        paint.setShadowLayer(24f * resources.displayMetrics.density, 0f, 0f, 0x5520B8FF)
        canvas.drawBitmap(core, null, RectF(left, top, left + side, top + side), paint)
    }
}
