package ai.personal.companion

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.os.SystemClock
import android.view.View
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * True 3D-coordinate neural network projected onto Android Canvas.
 * The same canonical artwork is retained as a subdued visual reference,
 * while depth-sorted nodes and links actually rotate through perspective.
 */
internal class VishnuGenesisCoreView(context: Context) : View(context) {
    private data class Node(val x: Float, val y: Float, val z: Float, val radius: Float)
    private data class Projected(val x: Float, val y: Float, val z: Float, val r: Float)
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val artwork = BitmapFactory.decodeResource(resources, R.drawable.vishnu_genesis_core)
    private val nodes: List<Node>
    private val edges: List<Pair<Int, Int>>
    private val density = resources.displayMetrics.density

    init {
        contentDescription = "Animated Vishnu 3D intelligence core"
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        minimumHeight = (190 * density).toInt()
        setLayerType(LAYER_TYPE_SOFTWARE, null)
        val golden = PI * (3 - sqrt(5.0))
        nodes = (0 until 165).map { i ->
            val y = 1.0 - 2.0 * i / 164.0
            val circle = sqrt((1.0 - y * y).coerceAtLeast(0.0))
            val inner = if (i % 5 == 0) 0.55 else 1.0
            val theta = golden * i
            Node(
                (cos(theta) * circle * inner).toFloat(),
                (y * inner).toFloat(),
                (sin(theta) * circle * inner).toFloat(),
                if (i % 13 == 0) 2.5f else 1.15f
            )
        }
        val links = mutableListOf<Pair<Int, Int>>()
        nodes.forEachIndexed { i, a ->
            val closest = nodes.indices.asSequence().filter { it != i }
                .map { j ->
                    val n = nodes[j]
                    val dx = a.x - n.x; val dy = a.y - n.y; val dz = a.z - n.z
                    j to dx * dx + dy * dy + dz * dz
                }
                .filter { it.second < .23f }
                .sortedBy { it.second }
                .take(3)
            for ((j, _) in closest) if (j > i) links.add(i to j)
        }
        edges = links
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val side = min(width, height).toFloat()
        if (side <= 0f) return
        val left = (width - side) / 2f
        val top = (height - side) / 2f
        val paused = !ValueAnimator.areAnimatorsEnabled()
        val angle = if (paused) 0f else (SystemClock.uptimeMillis() % 48000L) / 48000f * (2 * PI).toFloat()
        val ca = cos(angle); val sa = sin(angle)
        val centerX = left + side / 2f; val centerY = top + side / 2f
        val radius = side * .40f

        // The approved reference provides a gentle halo, never a fake moving mesh.
        paint.style = Paint.Style.FILL
        paint.alpha = 52
        paint.clearShadowLayer()
        canvas.drawBitmap(artwork, null, RectF(left, top, left + side, top + side), paint)
        val projected = nodes.map { n ->
            val x = n.x * ca - n.z * sa
            val z = n.x * sa + n.z * ca
            val depth = 2.65f / (2.65f - z * .38f)
            Projected(centerX + x * radius * depth,
                centerY + n.y * radius * depth, z, n.radius * density * depth)
        }

        paint.style = Paint.Style.STROKE
        paint.strokeWidth = (.85f * density).coerceAtMost(side / 300f)
        for ((i, j) in edges) {
            val a = projected[i]; val b = projected[j]
            val opacity = ((a.z + b.z + 2f) * 23 + 25).toInt().coerceIn(18, 115)
            paint.color = Color.argb(opacity, 57, 190, 255)
            canvas.drawLine(a.x, a.y, b.x, b.y, paint)
        }

        paint.style = Paint.Style.STROKE
        paint.strokeWidth = 1.1f * density
        paint.color = Color.argb(110, 47, 207, 255)
        canvas.drawCircle(centerX, centerY, radius, paint)

        paint.style = Paint.Style.FILL
        projected.forEachIndexed { i, n ->
            val opacity = ((n.z + 1f) * 66 + 75).toInt().coerceIn(55, 210)
            paint.color = Color.argb(opacity, if (i % 13 == 0) 178 else 60, 221, 255)
            if (i % 13 == 0) paint.setShadowLayer(8f * density, 0f, 0f, Color.argb(150, 0, 194, 255))
            canvas.drawCircle(n.x, n.y, n.r, paint)
            paint.clearShadowLayer()
        }
        if (isAttachedToWindow && !paused && visibility == VISIBLE) postInvalidateDelayed(33L)
    }
}
