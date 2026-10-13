package ai.personal.companion

import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class ConnectActivity : AppCompatActivity() {
    companion object {
        private const val MAX_RESPONSE_BYTES = 1_048_576
    }

    private val client = OkHttpClient.Builder()
        .callTimeout(15, TimeUnit.SECONDS)
        .retryOnConnectionFailure(false)
        .followRedirects(false)
        .followSslRedirects(false)
        .build()

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

    private lateinit var status: TextView
    private lateinit var manualBox: LinearLayout
    private lateinit var base: EditText
    private lateinit var token: EditText
    private lateinit var code: EditText
    private lateinit var allowLocalDevelopment: CheckBox

    private val scanner = registerForActivityResult(ScanContract()) { result ->
        val contents = result.contents
        if (contents.isNullOrBlank()) {
            status.text = "QR scan cancelled. You can scan again or enter the connection details manually."
            return@registerForActivityResult
        }
        try {
            val payload = PairingPayloadParser.parse(contents, allowLocalDevelopment.isChecked)
            base.setText(payload.baseUrl)
            token.setText(payload.token)
            code.setText(payload.code)
            status.text = "Vishnu found. Connecting this Android device…"
            pair(payload.baseUrl, payload.token, payload.code)
        } catch (exc: IllegalArgumentException) {
            status.text = exc.message ?: "That QR code is not a valid Vishnu connection offer."
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!prefs.getString("device", null).isNullOrBlank() && !prefs.getString("bearer", null).isNullOrBlank()) {
            openVishnu()
            return
        }

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(28), dp(34), dp(28), dp(34))
            setBackgroundColor(PersonalAITheme.ColorToken.background)
        }
        val brand = TextView(this).apply {
            text = "V I S H N U"
            textSize = 13f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
        }
        val title = TextView(this).apply {
            text = "Connect to my Vishnu"
            textSize = 30f
            setTextColor(PersonalAITheme.ColorToken.text)
            setPadding(0, dp(18), 0, dp(10))
        }
        val copy = TextView(this).apply {
            text = "Scan the one-time QR shown by your primary Vishnu. This phone receives its own revocable device credential; your owner password and provider keys are never copied here."
            textSize = 15f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, 0, 0, dp(24))
        }
        val scan = Button(this).apply {
            text = "Scan Vishnu QR"
            contentDescription = "Scan the one-time Vishnu device connection QR code"
        }
        styleButton(scan, true)
        scan.setOnClickListener { launchScanner() }

        val manual = Button(this).apply { text = "Enter connection details instead" }
        styleButton(manual, false)

        allowLocalDevelopment = CheckBox(this).apply {
            text = "Allow insecure localhost development"
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            visibility = View.GONE
        }

        manualBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
            setPadding(0, dp(16), 0, 0)
        }
        base = EditText(this).apply {
            hint = "https://your-vishnu.example.com"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        token = EditText(this).apply {
            hint = "Connection key"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        code = EditText(this).apply {
            hint = "6-digit code"
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
        }
        listOf(base, token, code).forEach(::styleField)
        val connect = Button(this).apply { text = "Connect this device" }
        styleButton(connect, true)
        connect.setOnClickListener { pairManual() }
        manualBox.addView(base)
        manualBox.addView(token)
        manualBox.addView(code)
        manualBox.addView(allowLocalDevelopment)
        manualBox.addView(connect)

        manual.setOnClickListener {
            val show = manualBox.visibility != View.VISIBLE
            manualBox.visibility = if (show) View.VISIBLE else View.GONE
            allowLocalDevelopment.visibility = if (show) View.VISIBLE else View.GONE
            manual.text = if (show) "Hide manual connection" else "Enter connection details instead"
        }

        status = TextView(this).apply {
            text = "Your primary Vishnu must be running and device pairing must be available."
            textSize = 13f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(20), 0, 0)
        }
        val safety = TextView(this).apply {
            text = "The QR expires automatically and can be used only once. If it expires, generate a new one from Vishnu."
            textSize = 12f
            setTextColor(Color.rgb(117, 135, 145))
            setPadding(0, dp(26), 0, 0)
        }

        root.addView(brand)
        root.addView(title)
        root.addView(copy)
        root.addView(scan)
        root.addView(manual)
        root.addView(manualBox)
        root.addView(status)
        root.addView(safety)
        setContentView(ScrollView(this).apply {
            isFillViewport = true
            addView(root)
        })
    }

    private fun launchScanner() {
        val options = ScanOptions().apply {
            setDesiredBarcodeFormats(ScanOptions.QR_CODE)
            setPrompt("Scan the QR shown by your Vishnu")
            setBeepEnabled(false)
            setOrientationLocked(false)
        }
        scanner.launch(options)
    }

    private fun pairManual() {
        try {
            val origin = PairingPayloadParser.normalizeOrigin(base.text.toString(), allowLocalDevelopment.isChecked)
            val pairingToken = token.text.toString().trim()
            val pairingCode = code.text.toString().trim()
            if (pairingToken.length !in 16..256) throw IllegalArgumentException("Enter the connection key shown by Vishnu")
            if (pairingCode.length != 6 || pairingCode.any { !it.isDigit() }) throw IllegalArgumentException("Enter the six-digit pairing code")
            pair(origin, pairingToken, pairingCode)
        } catch (exc: IllegalArgumentException) {
            status.text = exc.message ?: "Connection details are invalid."
        }
    }

    private fun pair(origin: String, pairingToken: String, pairingCode: String) {
        status.text = "Connecting securely…"
        val payload = JSONObject()
            .put("token", pairingToken)
            .put("code", pairingCode)
            .put("name", android.os.Build.MODEL.take(120))
            .put("platform", "android")
        val request = Request.Builder()
            .url("${origin.trimEnd('/')}/pair/confirm")
            .post(payload.toString().toRequestBody("application/json".toMediaType()))
            .header("Accept", "application/json")
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread { status.text = "Could not reach Vishnu. Check that it is running and both devices can reach the same secure address." }
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val text = try { boundedBody(it) } catch (_: Exception) {
                        runOnUiThread { status.text = "Vishnu returned an invalid or oversized pairing response." }
                        return
                    }
                    if (!it.isSuccessful) {
                        runOnUiThread {
                            status.text = if (it.code == 401) "That connection offer is invalid, expired, or already used. Generate a new QR in Vishnu." else "Vishnu rejected the connection (${it.code})."
                        }
                        return
                    }
                    val body = try { JSONObject(text) } catch (_: Exception) {
                        runOnUiThread { status.text = "Vishnu returned an invalid pairing response." }
                        return
                    }
                    val device = body.optJSONObject("device")?.optString("id").orEmpty()
                    val bearer = body.optString("bearer_token")
                    if (device.isBlank() || bearer.length < 16) {
                        runOnUiThread { status.text = "Vishnu did not return a valid device credential." }
                        return
                    }
                    prefs.edit()
                        .putString("base", origin)
                        .putString("device", device)
                        .putString("bearer", bearer)
                        .apply()
                    runOnUiThread {
                        token.setText("")
                        code.setText("")
                        status.text = "Connected. Opening Vishnu…"
                        openVishnu()
                    }
                }
            }
        })
    }

    private fun boundedBody(response: Response): String {
        val source = response.body?.source() ?: return "{}"
        source.request((MAX_RESPONSE_BYTES + 1).toLong())
        if (source.buffer.size > MAX_RESPONSE_BYTES.toLong()) throw IOException("response too large")
        return source.readUtf8()
    }

    private fun openVishnu() {
        startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP))
        finish()
    }

    private fun styleField(field: EditText) {
        field.setTextColor(PersonalAITheme.ColorToken.text)
        field.setHintTextColor(Color.rgb(116, 135, 145))
        field.background = rounded(PersonalAITheme.ColorToken.field, PersonalAITheme.ColorToken.border)
        field.setPadding(dp(14), dp(12), dp(14), dp(12))
        val params = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        params.bottomMargin = dp(10)
        field.layoutParams = params
    }

    private fun styleButton(button: Button, primary: Boolean) {
        val fill = if (primary) PersonalAITheme.ColorToken.primaryAction else PersonalAITheme.ColorToken.surface
        val ink = if (primary) PersonalAITheme.ColorToken.background else PersonalAITheme.ColorToken.text
        val stroke = if (primary) PersonalAITheme.ColorToken.primaryAction else PersonalAITheme.ColorToken.border
        button.background = rounded(fill, stroke)
        button.backgroundTintList = null
        button.setTextColor(ink)
        button.isAllCaps = false
        button.minHeight = dp(50)
        val params = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        params.bottomMargin = dp(10)
        button.layoutParams = params
    }

    private fun rounded(fill: Int, stroke: Int): GradientDrawable = GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        cornerRadius = dp(12).toFloat()
        setColor(fill)
        setStroke(dp(1), stroke)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
