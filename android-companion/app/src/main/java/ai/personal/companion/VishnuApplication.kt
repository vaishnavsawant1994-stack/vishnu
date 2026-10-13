package ai.personal.companion

import android.app.Activity
import android.app.Application
import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView

class VishnuApplication : Application(), Application.ActivityLifecycleCallbacks {
    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(this)
    }

    override fun onActivityResumed(activity: Activity) {
        if (activity is MainActivity) attachForgeButton(activity)
    }

    private fun attachForgeButton(activity: MainActivity) {
        val content = activity.findViewById<ViewGroup>(android.R.id.content) ?: return
        val scroll = (0 until content.childCount).map { content.getChildAt(it) }.filterIsInstance<ScrollView>().firstOrNull() ?: return
        val root = scroll.getChildAt(0) as? LinearLayout ?: return
        if ((0 until root.childCount).any { root.getChildAt(it).tag == FORGE_TAG }) return
        val density = activity.resources.displayMetrics.density
        fun dp(value: Int) = (value * density).toInt()
        val button = Button(activity).apply {
            tag = FORGE_TAG
            text = "Capability Forge V3"
            contentDescription = "Open Capability Forge V3 production-readiness controls"
            isAllCaps = false
            minHeight = dp(PersonalAITheme.touchTargetDp)
            setTextColor(PersonalAITheme.ColorToken.text)
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = dp(PersonalAITheme.cornerRadiusDp).toFloat()
                setColor(PersonalAITheme.ColorToken.surface)
                setStroke(dp(1), PersonalAITheme.ColorToken.border)
            }
            backgroundTintList = null
            setOnClickListener { activity.startActivity(Intent(activity, ForgeV3Activity::class.java)) }
        }
        val index = root.childCount.coerceAtMost(4)
        root.addView(button, index)
    }

    override fun onActivityCreated(activity: Activity, state: Bundle?) = Unit
    override fun onActivityStarted(activity: Activity) = Unit
    override fun onActivityPaused(activity: Activity) = Unit
    override fun onActivityStopped(activity: Activity) = Unit
    override fun onActivitySaveInstanceState(activity: Activity, state: Bundle) = Unit
    override fun onActivityDestroyed(activity: Activity) = Unit

    companion object { private const val FORGE_TAG = "vishnu-capability-forge-v3" }
}
