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
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException

class ConnectActivity : AppCompatActivity() {
    companion object {
        private const val MAX_RESPONSE_BYTES = 1_048_576
    }

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
            status.text = "QR scan cancelled. You can scan again or use the advanced fallback."
            return@registerForActivityResult
        }
        try {
            val payload = PairingPayloadParser.parse(contents, allowLocalDevelopment.isChecked)
            token.setText(payload.token)
            code.setText(payload.code)
            if (payload.zeroConfig) {
                status.text = "Finding your Vishnu automatically…"
                discoverAndPair(payload)
            } else {
                val origin = payload.baseUrl ?: throw IllegalArgumentException("The Vishnu address is missing")
                base.setText(origin)
                status.text = "Vishnu found. Connecting this Android device…"
                pair(origin, payload.token, payload.code, null, null)
            }
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
            text = "Scan the one-time QR shown by your primary Vishnu. The app finds the computer automatically on your local network and verifies its TLS identity before sending any pairing secret. No IP address or port is required."
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

        val manual = Button(this).apply { text = "Advanced manual fallback" }
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
            manual.text = if (show) "Hide advanced fallback" else "Advanced manual fallback"
        }

        status = TextView(this).apply {
            text = "Your primary Vishnu only needs to be running. Scan its secure connection QR to continue."
            textSize = 13f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(20), 0, 0)
        }
        val safety = TextView(this).apply {
            text = "The QR is one-use and expires automatically. Local discovery advertises no owner password, model key, memory, or device bearer credential."
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

    private fun discoverAndPair(payload: PairingPayload) {
        val serviceId = payload.serviceId ?: return
        val pin = payload.certSha256 ?: return
        VishnuDiscovery.discover(this, serviceId) { result ->
            runOnUiThread {
                result.onSuccess { origin ->
                    status.text = "Vishnu discovered. Verifying its secure identity…"
                    pair(origin, payload.token, payload.code, pin, serviceId)
                }.onFailure {
                    val fallback = payload.fallbackUrl
                    if (!fallback.isNullOrBlank()) {
                        status.text = "Local discovery unavailable. Trying the configured secure Vishnu endpoint…"
                        pair(fallback, payload.token, payload.code, null, null)
                    } else {
                        status.text = "Could not find this Vishnu on the local network. Make sure both devices are on the same Wi‑Fi, then scan a new QR."
                    }
                }
            }
        }
    }

    private fun pairManual() {
        try {
            val origin = PairingPayloadParser.normalizeOrigin(base.text.toString(), allowLocalDevelopment.isChecked)
            val pairingToken = token.text.toString().trim()
            val pairingCode = code.text.toString().trim()
            if (pairingToken.length !in 16..256) throw IllegalArgumentException("Enter the connection key shown by Vishnu")
            if (pairingCode.length != 6 || pairingCode.any { !it.isDigit() }) throw IllegalArgumentException("Enter the six-digit pairing code")
            pair(origin, pairingToken, pairingCode, null, null)
        } catch (exc: IllegalArgumentException) {
            status.text = exc.message ?: "Connection details are invalid."
        }
    }

    private fun pair(origin: String, pairingToken: String, pairingCode: String, tlsPin: String?, serviceId: String?) {
        status.text = if (tlsPin != null) "Verifying Vishnu and pairing securely…" else "Connecting securely…"
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
        PinnedTls.client(tlsPin).newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread {
                    status.text = if (tlsPin != null) {
                        "Secure Vishnu verification failed. The app did not send credentials to an unverified device. Generate a new QR and retry."
                    } else {
                        "Could not reach Vishnu. Check the secure endpoint and retry."
                    }
                }
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
                    val edit = prefs.edit()
                        .putString("base", origin)
                        .putString("device", device)
                        .putString("bearer", bearer)
                    if (tlsPin != null && serviceId != null) {
                        edit.putString("tls_pin", tlsPin).putString("service_id", serviceId)
                    } else {
                        edit.remove("tls_pin").remove("service_id")
                    }
                    edit.apply()
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