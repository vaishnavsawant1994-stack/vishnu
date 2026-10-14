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
        if (activity is MainActivity) {
            attachPasskeyButton(activity)
            attachForgeButton(activity)
        }
    }

    private fun attachPasskeyButton(activity: MainActivity) {
        val root = mainRoot(activity) ?: return
        if ((0 until root.childCount).any { root.getChildAt(it).tag == PASSKEY_TAG }) return
        val button = surfaceButton(activity).apply {
            tag = PASSKEY_TAG
            text = "Protect Vishnu with a passkey"
            contentDescription = "Create an Android passkey for the Vishnu owner"
            setOnClickListener { activity.startActivity(Intent(activity, PasskeySetupActivity::class.java)) }
        }
        val index = root.childCount.coerceAtMost(4)
        root.addView(button, index)
    }

    private fun attachForgeButton(activity: MainActivity) {
        val root = mainRoot(activity) ?: return
        if ((0 until root.childCount).any { root.getChildAt(it).tag == FORGE_TAG }) return
        val button = surfaceButton(activity).apply {
            tag = FORGE_TAG
            text = "Capability Forge V3"
            contentDescription = "Open Capability Forge V3 production-readiness controls"
            setOnClickListener { activity.startActivity(Intent(activity, ForgeV3Activity::class.java)) }
        }
        val index = root.childCount.coerceAtMost(5)
        root.addView(button, index)
    }

    private fun mainRoot(activity: MainActivity): LinearLayout? {
        val content = activity.findViewById<ViewGroup>(android.R.id.content) ?: return null
        val scroll = (0 until content.childCount)
            .map { content.getChildAt(it) }
            .filterIsInstance<ScrollView>()
            .firstOrNull() ?: return null
        return scroll.getChildAt(0) as? LinearLayout
    }

    private fun surfaceButton(activity: MainActivity): Button {
        val density = activity.resources.displayMetrics.density
        fun dp(value: Int) = (value * density).toInt()
        return Button(activity).apply {
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
        }
    }

    override fun onActivityCreated(activity: Activity, state: Bundle?) = Unit
    override fun onActivityStarted(activity: Activity) = Unit
    override fun onActivityPaused(activity: Activity) = Unit
    override fun onActivityStopped(activity: Activity) = Unit
    override fun onActivitySaveInstanceState(activity: Activity, state: Bundle) = Unit
    override fun onActivityDestroyed(activity: Activity) = Unit

    companion object {
        private const val PASSKEY_TAG = "vishnu-native-passkey"
        private const val FORGE_TAG = "vishnu-capability-forge-v3"
    }
}