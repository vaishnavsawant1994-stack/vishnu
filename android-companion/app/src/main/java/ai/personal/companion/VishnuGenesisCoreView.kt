package ai.personal.companion

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.os.SystemClock
import android.provider.Settings
import android.view.MotionEvent
import android.view.View
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * Canonical Vishnu core, with a deterministic 3D-rotating cyan network overlay.
 * The shared transparent image keeps the owner's approved visual identity,
 * while the perspective-projected links and nodes rotate in 3D.
 * Motion stops while detached or when system animation is disabled.
 */
internal class VishnuGenesisCoreView(context: Context) : View(context) {
    private data class Point3(val x: Float, val y: Float, val z: Float)
    private data class Projected(val x: Float, val y: Float, val z: Float)
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val core = BitmapFactory.decodeResource(resources, R.drawable.vishnu_genesis_core)
    private val nodes = List(62) { index ->
        val y = 1f - 2f * (index + 0.5f) / 62f
        val ring = kotlin.math.sqrt((1f - y * y).coerceAtLeast(0f))
        val phi = index * 2.39996323f
        Point3((cos(phi) * ring).toFloat(), y, (sin(phi) * ring).toFloat())
    }
    private var originMillis = 0L
    private var offsetRadians = 0f
    private var animator: ValueAnimator? = null
    private var lastTouchX = 0f

    init {
        contentDescription = "Vishnu intelligence core, slowly rotating three-dimensional cyan network"
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        minimumHeight = (190 * resources.displayMetrics.density).toInt()
        setLayerType(LAYER_TYPE_SOFTWARE, null)
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        val scale = runCatching {
            Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f)
        }.getOrDefault(1f)
        if (scale <= 0f || !ValueAnimator.areAnimatorsEnabled()) return
        originMillis = SystemClock.uptimeMillis()
        animator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 32000L
            repeatCount = ValueAnimator.INFINITE
            interpolator = android.view.animation.LinearInterpolator()
            addUpdateListener { invalidate() }
            start()
        }
    }

    override fun onDetachedFromWindow() {
        animator?.cancel()
        animator = null
        super.onDetachedFromWindow()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> { lastTouchX = event.x; return true }
            MotionEvent.ACTION_MOVE -> {
                offsetRadians += (event.x - lastTouchX) / width.coerceAtLeast(1) * 2.2f
                lastTouchX = event.x
                invalidate()
                return true
            }
            MotionEvent.ACTION_UP -> { performClick(); return true }
        }
        return super.onTouchEvent(event)
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val side = minOf(width, height).toFloat()
        if (side <= 0f) return
        val left = (width - side) / 2f
        val top = (height - side) / 2f
        paint.setShadowLayer(19f * resources.displayMetrics.density, 0f, 0f, 0x4020B8FF)
        canvas.drawBitmap(core, null, RectF(left, top, left + side, top + side), paint)
        paint.clearShadowLayer()

        val radius = side * 0.40f
        val midX = width * 0.5f
        val midY = height * 0.5f
        val phase = offsetRadians + (animator?.animatedFraction ?: 0f) * (2f * PI.toFloat())
        val projected = nodes.map { p ->
            val x = p.x * cos(phase) + p.z * sin(phase)
            val z = p.z * cos(phase) - p.x * sin(phase)
            val perspective = 2.6f / (2.6f - z * .55f)
            Projected(midX + x * radius * perspective, midY + p.y * radius * perspective, z)
        }
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = (side / 650f).coerceAtLeast(0.6f)
        for (i in projected.indices) {
            val from = projected[i]
            val start = (i + 1) % projected.size
            for (target in listOf(start, (i + 9) % projected.size)) {
                val to = projected[target]
                val alpha = if (from.z + to.z > 0f) 74 else 20
                paint.color = Color.argb(alpha, 70, 210, 255)
                canvas.drawLine(from.x, from.y, to.x, to.y, paint)
            }
        }
        paint.style = Paint.Style.FILL
        for (point in projected) {
            val front = (point.z + 1f) / 2f
            paint.color = Color.argb((62 + front * 160).toInt().coerceIn(0,255), 60, 221, 255)
            canvas.drawCircle(point.x, point.y, side * (0.002f + front * 0.004f), paint)
        }
    }
}
