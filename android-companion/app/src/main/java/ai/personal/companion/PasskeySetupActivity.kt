package ai.personal.companion

import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.credentials.CreateCredentialResponse
import androidx.credentials.CreatePublicKeyCredentialRequest
import androidx.credentials.CreatePublicKeyCredentialResponse
import androidx.credentials.CredentialManager
import androidx.credentials.CredentialManagerCallback
import androidx.credentials.exceptions.CreateCredentialException
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException

class PasskeySetupActivity : AppCompatActivity() {
    companion object { private const val MAX_RESPONSE_BYTES = 1_048_576 }

    private lateinit var status: TextView
    private lateinit var create: Button
    private val credentialManager by lazy { CredentialManager.create(this) }
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(32), dp(24), dp(32))
            setBackgroundColor(PersonalAITheme.ColorToken.background)
        }
        val title = TextView(this).apply {
            text = "Protect Vishnu with a passkey"
            textSize = 26f
            setTextColor(PersonalAITheme.ColorToken.text)
        }
        val copy = TextView(this).apply {
            text = "Android Credential Manager creates a phishing-resistant passkey protected by your phone security. Vishnu stores only the public credential."
            textSize = 15f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(12), 0, dp(22))
        }
        create = Button(this).apply {
            text = "Create passkey"
            isAllCaps = false
            setOnClickListener { beginPasskey() }
        }
        styleButton(create)
        status = TextView(this).apply {
            text = if (prefs.getBoolean("native_passkey_registered", false))
                "A native passkey was registered from this phone. You can create another if you want a replacement credential."
            else "Your existing owner password and recovery codes remain available as fallback methods."
            textSize = 13f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(14), 0, 0)
        }
        root.addView(title); root.addView(copy); root.addView(create); root.addView(status)
        setContentView(ScrollView(this).apply { isFillViewport = true; addView(root) })
    }

    private fun beginPasskey() {
        val origin = prefs.getString("base", "")?.trim()?.trimEnd('/').orEmpty()
        val device = prefs.getString("device", "").orEmpty()
        val bearer = prefs.getString("bearer", "").orEmpty()
        if (!origin.startsWith("https://") || device.isBlank() || bearer.length < 32) {
            status.text = "Connect this phone to your Vishnu over HTTPS before creating a passkey."
            return
        }
        create.isEnabled = false
        status.text = "Requesting a one-time passkey challenge from Vishnu…"
        val body = JSONObject().put("device_id", device).put("device_token", bearer).put("platform", "android")
        val request = Request.Builder()
            .url("$origin/iphone/api/native/passkeys/register/options")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .header("Accept", "application/json")
            .build()
        PinnedTls.client(prefs.getString("tls_pin", null)).newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) = runOnUiThread {
                create.isEnabled = true
                status.text = "Could not reach Vishnu securely. Check the runtime and try again."
            }
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val raw = try { boundedBody(it) } catch (_: Exception) { "" }
                    if (!it.isSuccessful) {
                        runOnUiThread {
                            create.isEnabled = true
                            status.text = when (it.code) {
                                401, 403 -> "This phone is no longer authorized to manage owner security."
                                409 -> "Native passkeys are not enabled for this Vishnu runtime yet. Configure its signed Android Digital Asset Link first."
                                else -> "Vishnu could not start passkey setup (${it.code})."
                            }
                        }
                        return
                    }
                    val result = try { JSONObject(raw) } catch (_: Exception) { null }
                    val challengeId = result?.optString("challenge_id").orEmpty()
                    val options = result?.optJSONObject("public_key")
                    if (challengeId.isBlank() || options == null) {
                        runOnUiThread { create.isEnabled = true; status.text = "Vishnu returned an invalid passkey challenge." }
                        return
                    }
                    runOnUiThread { launchCredentialManager(origin, device, bearer, challengeId, options) }
                }
            }
        })
    }

    private fun launchCredentialManager(origin: String, device: String, bearer: String,
                                        challengeId: String, options: JSONObject) {
        status.text = "Confirm the passkey with your phone security."
        val request = try { CreatePublicKeyCredentialRequest(options.toString()) } catch (_: Exception) {
            create.isEnabled = true
            status.text = "The passkey challenge from Vishnu was invalid."
            return
        }
        credentialManager.createCredentialAsync(
            this,
            request,
            null,
            ContextCompat.getMainExecutor(this),
            object : CredentialManagerCallback<CreateCredentialResponse, CreateCredentialException> {
                override fun onResult(result: CreateCredentialResponse) {
                    val publicKey = result as? CreatePublicKeyCredentialResponse
                    if (publicKey == null) {
                        create.isEnabled = true
                        status.text = "Android did not return a public-key credential."
                        return
                    }
                    completeRegistration(origin, device, bearer, challengeId, publicKey.registrationResponseJson)
                }
                override fun onError(e: CreateCredentialException) {
                    create.isEnabled = true
                    status.text = "Passkey creation was cancelled or unavailable on this device."
                }
            },
        )
    }

    private fun completeRegistration(origin: String, device: String, bearer: String,
                                     challengeId: String, registrationJson: String) {
        val credential = try { JSONObject(registrationJson) } catch (_: Exception) {
            create.isEnabled = true
            status.text = "Android returned an invalid passkey response."
            return
        }
        val body = JSONObject()
            .put("device_id", device)
            .put("device_token", bearer)
            .put("platform", "android")
            .put("challenge_id", challengeId)
            .put("credential", credential)
            .put("name", "Android passkey")
        val request = Request.Builder()
            .url("$origin/iphone/api/native/passkeys/register/complete")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .header("Accept", "application/json")
            .build()
        status.text = "Verifying the passkey with Vishnu…"
        PinnedTls.client(prefs.getString("tls_pin", null)).newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) = runOnUiThread {
                create.isEnabled = true
                status.text = "The passkey was created on Android, but Vishnu could not verify it. Start setup again to register a fresh credential."
            }
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    runCatching { boundedBody(it) }
                    runOnUiThread {
                        create.isEnabled = true
                        if (!it.isSuccessful) {
                            status.text = "Vishnu rejected the passkey verification (${it.code}). Start again."
                            return@runOnUiThread
                        }
                        prefs.edit().putBoolean("native_passkey_registered", true).apply()
                        status.text = "Passkey registered. Your private key remains protected by Android Credential Manager."
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

    private fun styleButton(button: Button) {
        button.setTextColor(PersonalAITheme.ColorToken.background)
        button.background = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dp(12).toFloat()
            setColor(PersonalAITheme.ColorToken.primaryAction)
        }
        button.backgroundTintList = null
        button.minHeight = dp(50)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}