package ai.personal.companion

import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
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
import java.util.concurrent.TimeUnit

class ForgeV3Activity : AppCompatActivity() {
    private val client = OkHttpClient.Builder()
        .callTimeout(15, TimeUnit.SECONDS)
        .retryOnConnectionFailure(false)
        .followRedirects(false)
        .followSslRedirects(false)
        .build()

    private lateinit var status: TextView
    private lateinit var result: TextView
    private lateinit var capabilityId: EditText
    private lateinit var version: EditText
    private lateinit var providerId: EditText
    private lateinit var targetStage: EditText
    private lateinit var approvalId: EditText
    private lateinit var buildId: EditText
    private lateinit var toolName: EditText
    private lateinit var parameters: EditText
    private lateinit var ownerPassword: EditText

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
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(24), dp(20), dp(32))
            setBackgroundColor(PersonalAITheme.ColorToken.background)
        }
        val title = TextView(this).apply {
            text = "Capability Forge V3"
            textSize = 24f
            setTextColor(PersonalAITheme.ColorToken.text)
        }
        val safety = TextView(this).apply {
            text = "Production-readiness controls only. No production activation authority is granted here. Mutations require a fresh owner verification."
            textSize = 13f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(8), 0, dp(16))
        }
        status = TextView(this).apply {
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            text = if (MainActivity.API_BASE.isBlank())
                "Forge V3 is disabled until a non-production Vishnu API and native callback are configured."
            else "Ready to inspect Forge V3 production-readiness state."
        }
        result = TextView(this).apply {
            setTextColor(PersonalAITheme.ColorToken.text)
            textSize = 12f
            setTextIsSelectable(true)
            setPadding(0, dp(12), 0, dp(18))
        }
        capabilityId = field("Capability ID")
        version = field("Version, for example 1.0.0")
        providerId = field("OAuth provider ID")
        targetStage = field("Rollout target: limited or broad_eligible").apply { setText("limited") }
        approvalId = field("Approved rollout ticket ID")
        buildId = field("Qualified Forge build ID")
        toolName = field("Read-only provider verification tool")
        parameters = field("JSON parameters").apply {
            setText("{}")
            minLines = 4
            gravity = Gravity.TOP
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        }
        ownerPassword = field("Owner password for fresh verification").apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }

        val back = button("Back") { finish() }
        val readiness = button("Refresh production readiness") { api("GET", "/owner/forge/v3/readiness") }
        val providers = button("List capability OAuth providers") { api("GET", "/owner/forge/v3/oauth/providers") }
        val oauthStatus = button("OAuth status for capability") {
            required(capabilityId, "Capability ID")?.let { api("GET", "/owner/forge/v3/oauth/${Uri.encode(it)}/status") }
        }
        val oauthStart = button("Start capability OAuth") {
            val cap = required(capabilityId, "Capability ID") ?: return@button
            val provider = required(providerId, "Provider ID") ?: return@button
            freshOwner {
                api("POST", "/owner/forge/v3/oauth/${Uri.encode(cap)}/${Uri.encode(provider)}/start", JSONObject()) { response ->
                    val url = response.optString("url", response.optString("authorization_url"))
                    if (url.startsWith("https://")) {
                        try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
                        catch (_: Exception) { status.text = "OAuth URL could not be opened. The response is shown below." }
                    }
                }
            }
        }
        val oauthRevoke = button("Revoke capability OAuth", destructive = true) {
            val cap = required(capabilityId, "Capability ID") ?: return@button
            val provider = required(providerId, "Provider ID") ?: return@button
            freshOwner { api("POST", "/owner/forge/v3/oauth/${Uri.encode(cap)}/${Uri.encode(provider)}/revoke", JSONObject()) }
        }
        val rollout = button("Inspect rollout state") {
            val cap = required(capabilityId, "Capability ID") ?: return@button
            val ver = required(version, "Version") ?: return@button
            api("GET", "/owner/forge/v3/rollout/${Uri.encode(cap)}/${Uri.encode(ver)}")
        }
        val canary = button("Run pre-activation canary") {
            val cap = required(capabilityId, "Capability ID") ?: return@button
            val ver = required(version, "Version") ?: return@button
            val build = required(buildId, "Build ID") ?: return@button
            val params = jsonParameters() ?: return@button
            freshOwner {
                api("POST", "/owner/forge/v3/rollout/${Uri.encode(cap)}/${Uri.encode(ver)}/canary",
                    JSONObject().put("build_id", build).put("parameters", params))
            }
        }
        val requestPromotion = button("Request rollout promotion") {
            val cap = required(capabilityId, "Capability ID") ?: return@button
            val ver = required(version, "Version") ?: return@button
            val target = required(targetStage, "Target stage") ?: return@button
            freshOwner {
                api("POST", "/owner/forge/v3/rollout/${Uri.encode(cap)}/${Uri.encode(ver)}/promotion",
                    JSONObject().put("target_stage", target)) { response ->
                    val ticket = response.optString("approval_id")
                    if (ticket.isNotBlank()) approvalId.setText(ticket)
                }
            }
        }
        val commitPromotion = button("Commit owner-approved promotion") {
            val cap = required(capabilityId, "Capability ID") ?: return@button
            val ver = required(version, "Version") ?: return@button
            val target = required(targetStage, "Target stage") ?: return@button
            val ticket = required(approvalId, "Approved ticket ID") ?: return@button
            freshOwner {
                api("POST", "/owner/forge/v3/rollout/${Uri.encode(cap)}/${Uri.encode(ver)}/promotion",
                    JSONObject().put("target_stage", target).put("ticket_id", ticket))
            }
        }
        val health = button("Evaluate active health") {
            val cap = required(capabilityId, "Capability ID") ?: return@button
            val ver = required(version, "Version") ?: return@button
            freshOwner { api("POST", "/owner/forge/v3/health/${Uri.encode(cap)}/${Uri.encode(ver)}", JSONObject()) }
        }
        val verifyProvider = button("Verify live provider through read-only tool") {
            val tool = required(toolName, "Verification tool") ?: return@button
            val params = jsonParameters() ?: return@button
            val body = JSONObject().put("tool_name", tool).put("parameters", params)
            capabilityId.text.toString().trim().takeIf { it.isNotBlank() }?.let { body.put("capability_id", it) }
            version.text.toString().trim().takeIf { it.isNotBlank() }?.let { body.put("version", it) }
            freshOwner { api("POST", "/owner/forge/v3/providers/verify", body) }
        }

        listOf(title, safety, status, readiness, providers, capabilityId, version, providerId, oauthStatus,
            ownerPassword, oauthStart, oauthRevoke, targetStage, approvalId, buildId, rollout, canary,
            requestPromotion, commitPromotion, health, toolName, parameters, verifyProvider, result, back)
            .forEach(root::addView)
        setContentView(ScrollView(this).apply { isFillViewport = true; addView(root) })
    }

    private fun field(hintText: String): EditText = EditText(this).apply {
        hint = hintText
        setTextColor(PersonalAITheme.ColorToken.text)
        setHintTextColor(Color.rgb(135, 151, 162))
        setPadding(dp(12), dp(10), dp(12), dp(10))
        inputType = InputType.TYPE_CLASS_TEXT
        minHeight = dp(48)
    }

    private fun button(label: String, destructive: Boolean = false, action: () -> Unit): Button = Button(this).apply {
        text = label
        isAllCaps = false
        minHeight = dp(48)
        setTextColor(if (destructive) Color.rgb(255, 170, 170) else PersonalAITheme.ColorToken.text)
        setOnClickListener { action() }
    }

    private fun required(field: EditText, label: String): String? {
        val value = field.text.toString().trim()
        if (value.isBlank()) status.text = "$label is required."
        return value.takeIf { it.isNotBlank() }
    }

    private fun jsonParameters(): JSONObject? = try {
        JSONObject(parameters.text.toString().ifBlank { "{}" })
    } catch (_: Exception) {
        status.text = "Parameters must be a JSON object."
        null
    }

    private fun freshOwner(action: () -> Unit) {
        val password = ownerPassword.text.toString()
        if (password.isBlank()) {
            status.text = "Enter the owner password to create a fresh verification window."
            return
        }
        api("POST", "/native/sessions/reauth", JSONObject().put("password", password), show = false) {
            ownerPassword.setText("")
            action()
        }
    }

    private fun api(method: String, path: String, payload: JSONObject? = null, show: Boolean = true,
                    after: ((JSONObject) -> Unit)? = null) {
        if (MainActivity.API_BASE.isBlank()) {
            status.text = "Forge V3 is disabled until a non-production Vishnu API is configured."
            return
        }
        val token = prefs.getString("native_access_token", null)
        if (token.isNullOrBlank() || prefs.getLong("native_expires_at", 0L) <= System.currentTimeMillis()) {
            status.text = "Native owner session expired. Return to Universal Capabilities and sign in again."
            return
        }
        val builder = Request.Builder().url(MainActivity.API_BASE + path)
            .header("Authorization", "Bearer $token")
            .header("Accept", "application/json")
        val body = payload?.toString()?.toRequestBody("application/json".toMediaType())
        val request = when (method) {
            "GET" -> builder.get().build()
            "POST" -> builder.post(body ?: "{}".toRequestBody("application/json".toMediaType())).build()
            else -> return
        }
        status.text = "Contacting Vishnu…"
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread { status.text = "Vishnu could not complete the request." }
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val text = try { boundedBody(it) } catch (_: Exception) {
                        runOnUiThread { status.text = "Vishnu returned an invalid or oversized response." }
                        return
                    }
                    val objectBody = try { JSONObject(text) } catch (_: Exception) { JSONObject().put("raw", text.take(2048)) }
                    runOnUiThread {
                        if (it.code == 401) {
                            prefs.edit().remove("native_access_token").remove("native_expires_at").apply()
                            status.text = "Native owner session expired or was revoked."
                            return@runOnUiThread
                        }
                        if (!it.isSuccessful) {
                            status.text = when (it.code) {
                                403 -> "Vishnu denied this Forge action."
                                409 -> "This action requires current evidence, approval, or a fresh owner verification."
                                else -> "Forge request failed (${it.code})."
                            }
                            result.text = objectBody.toString(2)
                            return@runOnUiThread
                        }
                        status.text = "Forge V3 request completed."
                        if (show) result.text = objectBody.toString(2)
                        after?.invoke(objectBody)
                    }
                }
            }
        })
    }

    private fun boundedBody(response: Response): String {
        val source = response.body?.source() ?: return "{}"
        source.request((MainActivity.MAX_API_RESPONSE_BYTES + 1).toLong())
        if (source.buffer.size > MainActivity.MAX_API_RESPONSE_BYTES.toLong()) throw IOException("response too large")
        return source.readUtf8()
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
