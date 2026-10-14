package ai.personal.companion

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.SecureRandom

/**
 * Owner-controlled bootstrap for people who do not already have a machine
 * hosting Vishnu. This activity never receives Render credentials and never
 * puts the Vishnu bootstrap secret in a URL.
 */
class RuntimeProvisioningActivity : AppCompatActivity() {
    private val prefs by lazy {
        val key = MasterKey.Builder(this).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
        EncryptedSharedPreferences.create(
            this,
            "personal_ai_device",
            key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    private lateinit var secretView: TextView
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(30), dp(24), dp(30))
            setBackgroundColor(PersonalAITheme.ColorToken.background)
        }
        root.addView(label("Create a secure Vishnu runtime", 27f, true))
        root.addView(label(
            "If this phone is your only device, you can create an owner-controlled HTTPS Vishnu runtime from your browser. " +
                "Render hosts the runtime, but it does not become your Vishnu identity or receive your owner password or recovery codes."
        ))
        root.addView(label(
            "Vishnu generates the one-time setup code on this phone. During Render setup, paste it only into PERSONAL_AI_OWNER_BOOTSTRAP_SECRET. " +
                "The code is never included in the deployment link."
        ))

        secretView = TextView(this).apply {
            text = ensureSecret()
            textSize = 14f
            setTextColor(PersonalAITheme.ColorToken.text)
            setTextIsSelectable(true)
            setPadding(dp(14), dp(14), dp(14), dp(14))
            background = rounded(PersonalAITheme.ColorToken.surface, PersonalAITheme.ColorToken.border)
        }
        root.addView(label("One-time setup code", 16f, true))
        root.addView(secretView)

        val copy = Button(this).apply {
            text = "Copy setup code"
            setOnClickListener { copySecret() }
        }
        styleButton(copy, false)
        root.addView(copy)

        val deploy = Button(this).apply {
            text = "Open secure runtime setup"
            contentDescription = "Open owner-approved Render deployment for a new Vishnu runtime"
            setOnClickListener {
                copySecret()
                val deployUri = Uri.Builder()
                    .scheme("https")
                    .authority("render.com")
                    .appendPath("deploy")
                    .appendQueryParameter("repo", "https://github.com/vaishnavsawant1994-stack/vishnu")
                    .build()
                startActivity(Intent(Intent.ACTION_VIEW, deployUri))
                status.text = "Setup code copied. In Render, paste it into PERSONAL_AI_OWNER_BOOTSTRAP_SECRET. After the deployment is live, copy its https://…onrender.com address, return to Create my Vishnu, and use this same setup code."
            }
        }
        styleButton(deploy, true)
        root.addView(deploy)

        val regenerate = Button(this).apply {
            text = "Generate a new setup code"
            setOnClickListener {
                val secret = randomSecret(48)
                prefs.edit().putString(PREF_BOOTSTRAP, secret).apply()
                secretView.text = secret
                status.text = "A new setup code was generated. Use only this newest code when creating the runtime."
            }
        }
        styleButton(regenerate, false)
        root.addView(regenerate)

        status = label("Your data directory is placed on the provider's persistent encrypted disk. Cloud hosting is optional; you can instead use any compatible self-hosted Vishnu runtime.")
        root.addView(status)

        val back = Button(this).apply {
            text = "Back to Vishnu setup"
            setOnClickListener { finish() }
        }
        styleButton(back, false)
        root.addView(back)

        setContentView(ScrollView(this).apply { isFillViewport = true; addView(root) })
    }

    private fun ensureSecret(): String {
        return prefs.getString(PREF_BOOTSTRAP, null)?.takeIf { it.length >= 32 }
            ?: randomSecret(48).also { prefs.edit().putString(PREF_BOOTSTRAP, it).apply() }
    }

    private fun copySecret() {
        val secret = secretView.text.toString()
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText("Vishnu one-time setup code", secret))
        status.text = "Setup code copied. Treat it like a temporary secret and paste it only into the Vishnu runtime deployment form."
    }

    private fun randomSecret(bytes: Int): String {
        val raw = ByteArray(bytes)
        SecureRandom().nextBytes(raw)
        return Base64.encodeToString(raw, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
    }

    private fun label(text: String, size: Float = 14f, strong: Boolean = false) = TextView(this).apply {
        this.text = text
        textSize = size
        setTextColor(if (strong) PersonalAITheme.ColorToken.text else PersonalAITheme.ColorToken.secondaryText)
        setPadding(0, dp(6), 0, dp(10))
    }

    private fun styleButton(button: Button, primary: Boolean) {
        button.isAllCaps = false
        button.minHeight = dp(50)
        button.setTextColor(if (primary) PersonalAITheme.ColorToken.background else PersonalAITheme.ColorToken.text)
        button.background = rounded(
            if (primary) PersonalAITheme.ColorToken.primaryAction else PersonalAITheme.ColorToken.surface,
            PersonalAITheme.ColorToken.border,
        )
        button.backgroundTintList = null
        val params = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        params.bottomMargin = dp(10)
        button.layoutParams = params
    }

    private fun rounded(fill: Int, border: Int) = GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        cornerRadius = dp(12).toFloat()
        setColor(fill)
        setStroke(dp(1), border)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    companion object {
        const val PREF_BOOTSTRAP = "pending_runtime_bootstrap_secret"
    }
}
