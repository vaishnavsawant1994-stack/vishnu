package ai.personal.companion

import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.ArrayAdapter
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okio.BufferedSink
import okio.source
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.security.SecureRandom
import java.util.UUID

class PortableRecoveryActivity : AppCompatActivity() {
    companion object { private const val MAX_RESPONSE_BYTES = 1_048_576 }

    private lateinit var base: EditText
    private lateinit var bootstrap: EditText
    private lateinit var passphrase: EditText
    private lateinit var password: EditText
    private lateinit var passwordAgain: EditText
    private lateinit var privacy: Spinner
    private lateinit var status: TextView
    private lateinit var archiveLabel: TextView
    private lateinit var keyLabel: TextView
    private lateinit var recoveryCodes: TextView
    private lateinit var recoverySaved: CheckBox
    private lateinit var scheduleButton: Button
    private lateinit var continueButton: Button
    private lateinit var finishButton: Button
    private var archiveUri: Uri? = null
    private var keyUri: Uri? = null

    private val prefs by lazy {
        val key = MasterKey.Builder(this).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
        EncryptedSharedPreferences.create(
            this, "personal_ai_device", key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }
    private val archivePicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        archiveUri = uri
        archiveLabel.text = uri?.lastPathSegment ?: "No recovery package selected"
    }
    private val keyPicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        keyUri = uri
        keyLabel.text = uri?.lastPathSegment ?: "No encrypted recovery key selected"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(30), dp(24), dp(30))
            setBackgroundColor(PersonalAITheme.ColorToken.background)
        }
        fun label(text: String, size: Float = 14f) = TextView(this).apply {
            this.text = text; textSize = size; setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(6), 0, dp(6))
        }
        root.addView(label("Restore Vishnu from a recovery package", 27f).apply { setTextColor(PersonalAITheme.ColorToken.text) })
        root.addView(label("Use the authenticated .vdr package and its separately encrypted recovery-key file. The passphrase is sent only to the fresh HTTPS runtime for validation and is never saved by this app."))

        base = field("Fresh Vishnu runtime URL (https://…)", false).apply { setText(prefs.getString("portable_restore_base", prefs.getString("base", "")) ?: "") }
        bootstrap = field("One-time runtime setup code", true)
        passphrase = field("Recovery-key passphrase", true)
        root.addView(base); root.addView(bootstrap); root.addView(passphrase)

        val chooseArchive = Button(this).apply { text = "Choose .vdr recovery package"; setOnClickListener { archivePicker.launch(arrayOf("application/octet-stream", "application/zip", "*/*")) } }
        val chooseKey = Button(this).apply { text = "Choose encrypted recovery-key file"; setOnClickListener { keyPicker.launch(arrayOf("application/octet-stream", "*/*")) } }
        styleButton(chooseArchive, false); styleButton(chooseKey, false)
        archiveLabel = label("No recovery package selected")
        keyLabel = label("No encrypted recovery key selected")
        root.addView(chooseArchive); root.addView(archiveLabel); root.addView(chooseKey); root.addView(keyLabel)

        scheduleButton = Button(this).apply { text = "Validate and schedule restore"; setOnClickListener { schedulePortableRestore() } }
        styleButton(scheduleButton, true); root.addView(scheduleButton)
        root.addView(label("After validation, restart the fresh Vishnu runtime. It restores owner data and stable identity metadata before starting. Then return here to create fresh security for the restored Vishnu."))

        root.addView(label("After the runtime restarts", 20f).apply { setTextColor(PersonalAITheme.ColorToken.text); setPadding(0, dp(22), 0, dp(8)) })
        password = field("New owner password (12 characters minimum)", true)
        passwordAgain = field("Confirm new owner password", true)
        root.addView(password); root.addView(passwordAgain)
        continueButton = Button(this).apply { text = "Create fresh owner security"; setOnClickListener { continueAfterRestart() } }
        styleButton(continueButton, true); root.addView(continueButton)

        recoveryCodes = TextView(this).apply {
            text = prefs.getString("portable_restore_recovery_codes", "") ?: ""
            textSize = 14f; setTextColor(PersonalAITheme.ColorToken.text); setTextIsSelectable(true)
            setPadding(dp(14), dp(14), dp(14), dp(14)); background = rounded(PersonalAITheme.ColorToken.surface, PersonalAITheme.ColorToken.border)
            visibility = if (text.isBlank()) View.GONE else View.VISIBLE
        }
        recoverySaved = CheckBox(this).apply { text = "I saved these new recovery codes somewhere separate from this phone"; setTextColor(PersonalAITheme.ColorToken.text); visibility = recoveryCodes.visibility }
        root.addView(recoveryCodes); root.addView(recoverySaved)

        privacy = Spinner(this).apply {
            adapter = ArrayAdapter(this@PortableRecoveryActivity, android.R.layout.simple_spinner_dropdown_item, listOf("local_preferred", "local_only", "external_allowed"))
            setSelection(0)
        }
        root.addView(label("Restored privacy default")); root.addView(privacy)
        finishButton = Button(this).apply { text = "Finish restored Vishnu"; setOnClickListener { finishRestoredSetup() }; visibility = recoveryCodes.visibility }
        styleButton(finishButton, true); root.addView(finishButton)

        status = label("Choose the two recovery files to begin.").apply { setPadding(0, dp(16), 0, 0) }
        root.addView(status)
        setContentView(ScrollView(this).apply { isFillViewport = true; addView(root) })
    }

    private fun schedulePortableRestore() {
        val origin = secureOrigin() ?: return
        val setupCode = bootstrap.text.toString()
        val phrase = passphrase.text.toString()
        val archive = archiveUri
        val key = keyUri
        if (setupCode.length < 32 || phrase.length < 12 || archive == null || key == null) {
            status.text = "Enter the setup code and recovery passphrase, and choose both recovery files."
            return
        }
        setBusy(true, "Uploading the encrypted recovery package…")
        uploadRaw(origin, "/iphone/api/native/recovery-package/archive", archive, setupCode) { first ->
            val session = first.optString("session_id")
            if (session.isBlank()) return@uploadRaw fail("Vishnu did not return a recovery upload session.")
            setStatus("Uploading the separate encrypted recovery key…")
            uploadRaw(origin, "/iphone/api/native/recovery-package/key?session_id=${Uri.encode(session)}", key, setupCode) {
                setStatus("Authenticating the recovery package…")
                val payload = JSONObject().put("session_id", session).put("bootstrap_secret", setupCode).put("passphrase", phrase)
                postJson(origin, "/iphone/api/native/recovery-package/schedule", payload) {
                    prefs.edit().putString("portable_restore_base", origin).apply()
                    setBusy(false, "Recovery package authenticated and scheduled. Restart that Vishnu runtime now; after it comes back, use ‘Create fresh owner security’ below.")
                }
            }
        }
    }

    private fun continueAfterRestart() {
        val origin = secureOrigin() ?: return
        val setupCode = bootstrap.text.toString()
        val first = password.text.toString(); val second = passwordAgain.text.toString()
        if (setupCode.length < 32 || first.length < 12 || first != second) {
            status.text = "Enter the same runtime setup code and matching new owner password."
            return
        }
        val device = prefs.getString("portable_restore_device_id", null) ?: UUID.randomUUID().toString().also { prefs.edit().putString("portable_restore_device_id", it).apply() }
        val token = prefs.getString("portable_restore_device_token", null) ?: randomSecret(48).also { prefs.edit().putString("portable_restore_device_token", it).apply() }
        val claim = prefs.getString("portable_restore_setup_claim", null) ?: randomSecret(48).also { prefs.edit().putString("portable_restore_setup_claim", it).apply() }
        val payload = JSONObject()
            .put("bootstrap_secret", setupCode).put("setup_claim", claim).put("password", first)
            .put("device_id", device).put("device_token", token).put("device_name", android.os.Build.MODEL ?: "Android")
            .put("platform", "android")
        setBusy(true, "Creating fresh owner security on the restored Vishnu…")
        postJson(origin, "/iphone/api/native/recovery-package/owner", payload) { result ->
            val codes = result.optJSONArray("recovery_codes") ?: JSONArray()
            if (codes.length() == 0) return@postJson fail("Vishnu did not return new recovery codes.")
            val text = (0 until codes.length()).joinToString("\n") { codes.optString(it) }
            prefs.edit().putString("portable_restore_recovery_codes", text).putString("portable_restore_base", origin).apply()
            runOnUiThread {
                recoveryCodes.text = text; recoveryCodes.visibility = View.VISIBLE
                recoverySaved.visibility = View.VISIBLE; finishButton.visibility = View.VISIBLE
                password.setText(""); passwordAgain.setText("")
                setBusy(false, "Fresh security created. Save the new recovery codes before finishing.")
            }
        }
    }

    private fun finishRestoredSetup() {
        if (!recoverySaved.isChecked) { status.text = "Save the new recovery codes before finishing."; return }
        val origin = prefs.getString("portable_restore_base", null) ?: return fail("Restored runtime address is missing.")
        val device = prefs.getString("portable_restore_device_id", null) ?: return fail("Restored device identity is missing.")
        val token = prefs.getString("portable_restore_device_token", null) ?: return fail("Restored device credential is missing.")
        val claim = prefs.getString("portable_restore_setup_claim", null) ?: return fail("Restored setup session is missing.")
        val payload = JSONObject().put("setup_claim", claim).put("device_id", device).put("device_token", token)
            .put("recovery_saved", true).put("privacy_mode", privacy.selectedItem.toString()).put("model_choice", "configure_later")
        setBusy(true, "Finishing the restored Vishnu…")
        postJson(origin, "/iphone/api/first-run/native/complete", payload) {
            prefs.edit()
                .putString("base", origin).putString("device", device).putString("bearer", token)
                .remove("portable_restore_device_id").remove("portable_restore_device_token")
                .remove("portable_restore_setup_claim").remove("portable_restore_recovery_codes")
                .remove("portable_restore_base").apply()
            runOnUiThread {
                setBusy(false, "Restore complete. This Android device is now a trusted owner device for the same Vishnu identity.")
                startActivity(Intent(this, MainActivity::class.java)); finish()
            }
        }
    }

    private fun uploadRaw(origin: String, path: String, uri: Uri, setupCode: String, done: (JSONObject) -> Unit) {
        val request = Request.Builder().url(origin + path).header("X-Vishnu-Bootstrap", setupCode)
            .header("Accept", "application/json").post(ContentUriBody(uri)).build()
        client().newCall(request).enqueue(jsonCallback(done))
    }

    private fun postJson(origin: String, path: String, payload: JSONObject, done: (JSONObject) -> Unit) {
        val request = Request.Builder().url(origin + path).header("Accept", "application/json")
            .post(payload.toString().toRequestBody("application/json".toMediaType())).build()
        client().newCall(request).enqueue(jsonCallback(done))
    }

    private fun jsonCallback(done: (JSONObject) -> Unit) = object : Callback {
        override fun onFailure(call: Call, e: IOException) = fail("Could not reach Vishnu securely. Check the runtime and try again.")
        override fun onResponse(call: Call, response: Response) {
            response.use {
                val raw = try { boundedBody(it) } catch (_: Exception) { "" }
                if (!it.isSuccessful) return fail(when (it.code) {
                    401 -> "The runtime setup code or recovery authorization was rejected."
                    409 -> "This runtime is not in the required recovery stage."
                    413 -> "The selected recovery file is larger than this recovery endpoint allows."
                    422 -> "The recovery package, encrypted key, passphrase, or setup data could not be authenticated."
                    else -> "Vishnu recovery request failed (${it.code})."
                })
                val json = try { JSONObject(raw) } catch (_: Exception) { return fail("Vishnu returned an invalid recovery response.") }
                done(json)
            }
        }
    }

    private inner class ContentUriBody(private val uri: Uri) : RequestBody() {
        override fun contentType(): MediaType = "application/octet-stream".toMediaType()
        override fun contentLength(): Long = try { contentResolver.openAssetFileDescriptor(uri, "r")?.use { it.length } ?: -1L } catch (_: Exception) { -1L }
        override fun writeTo(sink: BufferedSink) {
            val input = contentResolver.openInputStream(uri) ?: throw IOException("Cannot read selected recovery file")
            input.source().use { source -> sink.writeAll(source) }
        }
    }

    private fun client(): OkHttpClient = PinnedTls.client(null)

    private fun secureOrigin(): String? {
        val value = base.text.toString().trim().trimEnd('/')
        val uri = runCatching { Uri.parse(value) }.getOrNull()
        if (uri?.scheme != "https" || uri.host.isNullOrBlank()) { status.text = "Portable recovery requires a valid HTTPS Vishnu runtime URL."; return null }
        return value
    }

    private fun field(hint: String, secret: Boolean) = EditText(this).apply {
        this.hint = hint
        inputType = if (secret) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        setTextColor(PersonalAITheme.ColorToken.text); setHintTextColor(PersonalAITheme.ColorToken.secondaryText)
        background = rounded(PersonalAITheme.ColorToken.surface, PersonalAITheme.ColorToken.border); setPadding(dp(12), dp(10), dp(12), dp(10))
    }

    private fun styleButton(button: Button, primary: Boolean) {
        button.isAllCaps = false; button.minHeight = dp(50)
        button.setTextColor(if (primary) PersonalAITheme.ColorToken.background else PersonalAITheme.ColorToken.text)
        button.background = rounded(if (primary) PersonalAITheme.ColorToken.primaryAction else PersonalAITheme.ColorToken.surface, PersonalAITheme.ColorToken.border)
        button.backgroundTintList = null
    }

    private fun rounded(fill: Int, border: Int) = GradientDrawable().apply { shape = GradientDrawable.RECTANGLE; cornerRadius = dp(12).toFloat(); setColor(fill); setStroke(dp(1), border) }
    private fun setBusy(busy: Boolean, text: String) = runOnUiThread { scheduleButton.isEnabled = !busy; continueButton.isEnabled = !busy; finishButton.isEnabled = !busy; status.text = text }
    private fun setStatus(text: String) = runOnUiThread { status.text = text }
    private fun fail(text: String) { setBusy(false, text) }
    private fun randomSecret(bytes: Int): String { val raw = ByteArray(bytes); SecureRandom().nextBytes(raw); return android.util.Base64.encodeToString(raw, android.util.Base64.URL_SAFE or android.util.Base64.NO_WRAP or android.util.Base64.NO_PADDING) }
    private fun boundedBody(response: Response): String { val source = response.body?.source() ?: return "{}"; source.request((MAX_RESPONSE_BYTES + 1).toLong()); if (source.buffer.size > MAX_RESPONSE_BYTES) throw IOException("response too large"); return source.readUtf8() }
    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}