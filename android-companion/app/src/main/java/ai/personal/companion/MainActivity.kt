package ai.personal.companion

import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.ScrollView
import androidx.appcompat.app.AppCompatActivity
import androidx.browser.customtabs.CustomTabColorSchemeParams
import androidx.browser.customtabs.CustomTabsIntent
import androidx.core.content.ContextCompat
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException

class MainActivity : AppCompatActivity() {
    companion object {
        const val PERSONAL_AI_CLOUD_URL = "https://personal-ai-runtime-production.up.railway.app/iphone/"
        const val CAPABILITIES_URL = "https://personal-ai-runtime-production.up.railway.app/capabilities/"
    }

    private val client = OkHttpClient()
    private lateinit var status: TextView
    private lateinit var base: EditText
    private lateinit var pairToken: EditText
    private lateinit var code: EditText

    private val prefs by lazy {
        val key = MasterKey.Builder(this)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            this,
            "personal_ai_device",
            key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(PersonalAITheme.Space.x5), dp(28), dp(PersonalAITheme.Space.x5), dp(PersonalAITheme.Space.x8))
            setBackgroundColor(PersonalAITheme.ColorToken.background)
        }
        val brand = TextView(this).apply {
            text = "P E R S O N A L   A I"
            textSize = PersonalAITheme.Type.sectionTitle
            setTextColor(PersonalAITheme.ColorToken.text)
            setPadding(0, 0, 0, dp(10))
        }
        val description = TextView(this).apply {
            text = "Your owner-controlled intelligence"
            textSize = PersonalAITheme.Type.body
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, 0, 0, dp(26))
        }
        val openCloud = Button(this).apply {
            text = "Open Vishnu"
            contentDescription = "Open the secure Vishnu cloud experience"
        }
        val openCapabilities = Button(this).apply {
            text = "Manage Universal Capabilities"
            contentDescription = "Open Vishnu's owner authenticated capability manager"
        }
        val continuity = TextView(this).apply {
            text = "Voice, Google sign-in, memory and conversations continue securely in your trusted browser."
            textSize = PersonalAITheme.Type.supporting
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(dp(4), dp(14), dp(4), dp(26))
        }
        val advanced = Button(this).apply { text = "Advanced device pairing" }
        val pairingBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(Color.rgb(9, 17, 24), Color.rgb(35, 54, 66))
            setPadding(dp(14), dp(10), dp(14), dp(14))
            visibility = View.GONE
        }
        base = EditText(this).apply {
            hint = "http://PC:8766"
            setText(prefs.getString("base", "") ?: "")
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        pairToken = EditText(this).apply {
            hint = "Pairing token from desktop"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        code = EditText(this).apply {
            hint = "6-digit code"
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
        }
        status = TextView(this).apply {
            text = "Device companion is not paired"
            setTextColor(Color.rgb(148, 163, 184))
        setPadding(0, dp(PersonalAITheme.Space.x3), 0, 0)
        }
        val pair = Button(this).apply { text = "Pair" }
        val connect = Button(this).apply { text = "Start background connection" }
        listOf(base, pairToken, code).forEach(::styleField)
        listOf(openCloud, openCapabilities, pair, connect).forEach { styleButton(it, true) }
        styleButton(advanced, false)
        status.textSize = 13f
        status.setLineSpacing(dp(3).toFloat(), 1f)
        listOf(base, pairToken, code, pair, connect, status).forEach(pairingBox::addView)
        listOf(brand, description, openCloud, openCapabilities, continuity, advanced, pairingBox).forEach(box::addView)
        setContentView(ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
            addView(box)
        })
        openCloud.setOnClickListener { openPersonalAI() }
        openCapabilities.setOnClickListener { openUrl(CAPABILITIES_URL) }
        advanced.setOnClickListener {
            val show = pairingBox.visibility != View.VISIBLE
            pairingBox.visibility = if (show) View.VISIBLE else View.GONE
            advanced.text = if (show) "Hide device pairing" else "Advanced device pairing"
        }
        pair.setOnClickListener { pairDevice() }
        connect.setOnClickListener { startDeviceService() }
        if (prefs.getString("device", null) != null) startDeviceService()
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun rounded(fill: Int, stroke: Int): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
        cornerRadius = dp(PersonalAITheme.cornerRadiusDp).toFloat()
            setColor(fill)
            setStroke(dp(1), stroke)
        }

    private fun styleField(field: EditText) {
        field.setTextColor(PersonalAITheme.ColorToken.text)
        field.setHintTextColor(Color.rgb(135, 151, 162))
        field.background = rounded(PersonalAITheme.ColorToken.field, PersonalAITheme.ColorToken.border)
        field.setPadding(dp(PersonalAITheme.Space.x3), dp(PersonalAITheme.Space.x3), dp(PersonalAITheme.Space.x3), dp(PersonalAITheme.Space.x3))
        field.minHeight = dp(PersonalAITheme.controlHeightDp)
        field.textSize = PersonalAITheme.Type.body
    }

    private fun styleButton(button: Button, primary: Boolean) {
        val fill = if (primary) PersonalAITheme.ColorToken.primaryAction else PersonalAITheme.ColorToken.surface
        val ink = if (primary) PersonalAITheme.ColorToken.background else PersonalAITheme.ColorToken.text
        val stroke = if (primary) PersonalAITheme.ColorToken.primaryAction else PersonalAITheme.ColorToken.border
        button.background = rounded(fill, stroke)
        button.backgroundTintList = null
        button.setTextColor(ink)
        button.textSize = PersonalAITheme.Type.control
        button.isAllCaps = false
        button.minHeight = dp(PersonalAITheme.touchTargetDp)
        button.setPadding(dp(PersonalAITheme.Space.x4), dp(PersonalAITheme.Space.x2), dp(PersonalAITheme.Space.x4), dp(PersonalAITheme.Space.x2))
        button.stateListAnimator = null
    }

    private fun openPersonalAI() {
        openUrl(PERSONAL_AI_CLOUD_URL)
    }

    private fun openUrl(url: String) {
        val colors = CustomTabColorSchemeParams.Builder()
            .setToolbarColor(Color.rgb(3, 6, 13))
            .setNavigationBarColor(Color.rgb(3, 6, 13))
            .build()
        val customTab = CustomTabsIntent.Builder()
            .setDefaultColorSchemeParams(colors)
            .setShowTitle(false)
            .build()
        try {
            customTab.launchUrl(this, Uri.parse(url))
        } catch (_: Exception) {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        }
    }

    private fun pairDevice() {
        val payload = JSONObject()
        payload.put("token", pairToken.text.toString())
        payload.put("code", code.text.toString())
        payload.put("name", android.os.Build.MODEL)
        payload.put("platform", "android")
        val body = payload.toString().toRequestBody("application/json".toMediaType())
        val req = Request.Builder()
            .url(base.text.toString().trimEnd('/') + "/pair/confirm")
            .post(body)
            .build()
        client.newCall(req).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread { status.text = "Pair failed: ${e.message}" }
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val text = it.body?.string().orEmpty()
                    if (!it.isSuccessful) {
                        runOnUiThread { status.text = "Pair failed: $text" }
                        return
                    }
                    val obj = JSONObject(text)
                    val device = obj.getJSONObject("device").getString("id")
                    val bearer = obj.getString("bearer_token")
                    prefs.edit()
                        .putString("base", base.text.toString())
                        .putString("device", device)
                        .putString("bearer", bearer)
                        .apply()
                    runOnUiThread {
                        status.text = "Paired as $device"
                        startDeviceService()
                    }
                }
            }
        })
    }

    private fun startDeviceService() {
        if (prefs.getString("device", null) == null) {
            status.text = "Pair first"
            return
        }
        ContextCompat.startForegroundService(this, Intent(this, DeviceCommandService::class.java))
        status.text = "Background connection active"
    }
}
