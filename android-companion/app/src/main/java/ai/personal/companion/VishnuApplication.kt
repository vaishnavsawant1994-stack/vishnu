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
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import androidx.appcompat.app.AppCompatDelegate

class VishnuApplication : Application(), Application.ActivityLifecycleCallbacks {
    override fun onCreate() {
        super.onCreate()
        AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES)
        registerActivityLifecycleCallbacks(this)
    }

    override fun onActivityResumed(activity: Activity) {
        when (activity) {
            is MainActivity -> {
                clearConsumedRuntimeBootstrap(activity)
                attachPasskeyButton(activity)
                attachForgeButton(activity)
            }
            is ConnectActivity -> {
                attachRuntimeProvisioningButton(activity)
                attachPortableRecoveryButton(activity)
            }
        }
    }

    private fun clearConsumedRuntimeBootstrap(activity: Activity) {
        runCatching {
            val key = MasterKey.Builder(activity).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
            val prefs = EncryptedSharedPreferences.create(
                activity,
                "personal_ai_device",
                key,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            )
            if (!prefs.getString("device", null).isNullOrBlank() && !prefs.getString("bearer", null).isNullOrBlank()) {
                prefs.edit().remove(RuntimeProvisioningActivity.PREF_BOOTSTRAP).apply()
            }
        }
    }

    private fun attachRuntimeProvisioningButton(activity: ConnectActivity) {
        val root = activityRoot(activity) ?: return
        if ((0 until root.childCount).any { root.getChildAt(it).tag == RUNTIME_TAG }) return
        val button = surfaceButton(activity).apply {
            tag = RUNTIME_TAG
            text = "I don't have a Vishnu runtime yet"
            contentDescription = "Create an owner-controlled secure Vishnu runtime without a laptop"
            setOnClickListener { activity.startActivity(Intent(activity, RuntimeProvisioningActivity::class.java)) }
        }
        root.addView(button, root.childCount.coerceAtMost(5))
    }

    private fun attachPortableRecoveryButton(activity: ConnectActivity) {
        val root = activityRoot(activity) ?: return
        if ((0 until root.childCount).any { root.getChildAt(it).tag == RECOVERY_TAG }) return
        val button = surfaceButton(activity).apply {
            tag = RECOVERY_TAG
            text = "Restore from encrypted recovery package"
            contentDescription = "Restore Vishnu from a portable encrypted recovery package"
            setOnClickListener { activity.startActivity(Intent(activity, PortableRecoveryActivity::class.java)) }
        }
        root.addView(button, root.childCount.coerceAtMost(6))
    }

    private fun attachPasskeyButton(activity: MainActivity) {
        val root = activityRoot(activity) ?: return
        if ((0 until root.childCount).any { root.getChildAt(it).tag == PASSKEY_TAG }) return
        val button = surfaceButton(activity).apply {
            tag = PASSKEY_TAG
            text = "Protect Vishnu with a passkey"
            contentDescription = "Create an Android passkey for the Vishnu owner"
            setOnClickListener { activity.startActivity(Intent(activity, PasskeySetupActivity::class.java)) }
        }
        root.addView(button, root.childCount.coerceAtMost(4))
    }

    private fun attachForgeButton(activity: MainActivity) {
        val root = activityRoot(activity) ?: return
        if ((0 until root.childCount).any { root.getChildAt(it).tag == FORGE_TAG }) return
        val button = surfaceButton(activity).apply {
            tag = FORGE_TAG
            text = "Capability Forge V3"
            contentDescription = "Open Capability Forge V3 production-readiness controls"
            setOnClickListener { activity.startActivity(Intent(activity, ForgeV3Activity::class.java)) }
        }
        root.addView(button, root.childCount.coerceAtMost(5))
    }

    private fun activityRoot(activity: Activity): LinearLayout? {
        val content = activity.findViewById<ViewGroup>(android.R.id.content) ?: return null
        val scroll = (0 until content.childCount)
            .map { content.getChildAt(it) }
            .filterIsInstance<ScrollView>()
            .firstOrNull() ?: return null
        return scroll.getChildAt(0) as? LinearLayout
    }

    private fun surfaceButton(activity: Activity): Button {
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
        private const val RUNTIME_TAG = "vishnu-runtime-provisioning"
        private const val RECOVERY_TAG = "vishnu-portable-recovery"
        private const val PASSKEY_TAG = "vishnu-native-passkey"
        private const val FORGE_TAG = "vishnu-capability-forge-v3"
    }
}
