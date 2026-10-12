package ai.personal.companion

import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.util.Base64
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.ScrollView
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AlertDialog
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
import org.json.JSONArray
import java.io.IOException
import java.security.MessageDigest
import java.security.SecureRandom
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

class MainActivity : AppCompatActivity() {
    companion object {
        const val PERSONAL_AI_CLOUD_URL = "https://personal-ai-runtime-production.up.railway.app/iphone/"
        const val API_BASE = "https://personal-ai-runtime-production.up.railway.app/iphone/api"
        const val NATIVE_AUTH_URL = "https://personal-ai-runtime-production.up.railway.app/iphone/native/authorize"
        const val NATIVE_CLIENT_ID = "ai.personal.companion"
        const val NATIVE_REDIRECT = "https://personal-ai-runtime-production.up.railway.app/iphone/native/callback/android"
        const val MAX_API_RESPONSE_BYTES = 1_048_576
    }

    private val client = OkHttpClient.Builder().callTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
        .retryOnConnectionFailure(false).followRedirects(false).followSslRedirects(false).build()
    private lateinit var status: TextView
    private lateinit var root: LinearLayout
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
        root = LinearLayout(this).apply {
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
            contentDescription = "Sign in securely to manage Vishnu capabilities"
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
        listOf(brand, description, openCloud, openCapabilities, continuity, advanced, pairingBox).forEach(root::addView)
        setContentView(ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
            addView(root)
        })
        openCloud.setOnClickListener { openPersonalAI() }
        openCapabilities.setOnClickListener { manageCapabilities() }
        advanced.setOnClickListener {
            val show = pairingBox.visibility != View.VISIBLE
            pairingBox.visibility = if (show) View.VISIBLE else View.GONE
            advanced.text = if (show) "Hide device pairing" else "Advanced device pairing"
        }
        pair.setOnClickListener { pairDevice() }
        connect.setOnClickListener { startDeviceService() }
        if (prefs.getString("device", null) != null) startDeviceService()
        handleNativeCallback(intent?.data)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleNativeCallback(intent.data)
    }

    private fun manageCapabilities() {
        val expires = prefs.getLong("native_expires_at", 0L)
        val token = prefs.getString("native_access_token", null)
        if (token.isNullOrBlank() || expires <= System.currentTimeMillis()) {
            clearNativeSession()
            beginNativeAuthorization()
            return
        }
        showCapabilityList("")
    }

    private fun secureRandomText(): String {
        val bytes = ByteArray(32).also { SecureRandom().nextBytes(it) }
        return Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
    }

    private fun beginNativeAuthorization() {
        val verifier = secureRandomText()
        val stateValue = secureRandomText()
        val digest = MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(StandardCharsets.US_ASCII))
        val challenge = Base64.encodeToString(digest, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        prefs.edit().putString("native_pkce_verifier", verifier).putString("native_oauth_state", stateValue).apply()
        val authUrl = Uri.parse(NATIVE_AUTH_URL).buildUpon()
            .appendQueryParameter("client_id", NATIVE_CLIENT_ID)
            .appendQueryParameter("redirect_uri", NATIVE_REDIRECT)
            .appendQueryParameter("code_challenge", challenge)
            .appendQueryParameter("state", stateValue)
            .build().toString()
        status.text = "Continue in the secure browser to approve this device."
        openUrl(authUrl)
    }

    private fun handleNativeCallback(uri: Uri?) {
        if (uri == null || uri.scheme != "https" || uri.host != Uri.parse(NATIVE_REDIRECT).host ||
            uri.path != Uri.parse(NATIVE_REDIRECT).path) return
        val codeValue = uri.getQueryParameter("code")
        val returnedState = uri.getQueryParameter("state")
        val savedState = prefs.getString("native_oauth_state", null)
        val verifier = prefs.getString("native_pkce_verifier", null)
        if (codeValue.isNullOrBlank() || returnedState.isNullOrBlank() || savedState.isNullOrBlank() ||
            verifier.isNullOrBlank() || !MessageDigest.isEqual(returnedState.toByteArray(), savedState.toByteArray())) {
            clearNativeSession()
            status.text = "Sign-in could not be verified. Start again from Manage Universal Capabilities."
            return
        }
        val body = JSONObject().put("client_id", NATIVE_CLIENT_ID).put("redirect_uri", NATIVE_REDIRECT)
            .put("code", codeValue).put("code_verifier", verifier)
            .toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder().url("$API_BASE/native/sessions/exchange").post(body).build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread { status.text = "Secure sign-in could not reach Vishnu. Retry from Manage Universal Capabilities." }
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val safeBody = try { boundedBody(it) } catch (_: Exception) {
                        clearNativeSession()
                        runOnUiThread { status.text = "Vishnu returned an invalid or oversized sign-in response." }
                        return
                    }
                    if (!it.isSuccessful) {
                        clearNativeSession()
                        runOnUiThread { status.text = "Native sign-in was rejected. Sign in again and retry." }
                        return
                    }
                    val result = JSONObject(safeBody)
                    val token = result.optString("access_token")
                    val expires = System.currentTimeMillis() + result.optLong("expires_in", 0L) * 1000L
                    if (token.isBlank() || expires <= System.currentTimeMillis()) {
                        clearNativeSession()
                        runOnUiThread { status.text = "Vishnu returned an invalid session. Retry sign-in." }
                        return
                    }
                    prefs.edit().putString("native_access_token", token)
                        .putString("native_session_id", result.optString("session_id"))
                        .putString("native_scopes", result.optJSONArray("scopes")?.toString() ?: "[]")
                        .putLong("native_expires_at", expires)
                        .remove("native_pkce_verifier").remove("native_oauth_state").apply()
                    runOnUiThread { status.text = "Signed in securely. Loading capabilities…"; showCapabilityList("") }
                }
            }
        })
    }

    private fun clearNativeSession() {
        prefs.edit().remove("native_access_token").remove("native_session_id")
            .remove("native_scopes").remove("native_expires_at")
            .remove("native_pkce_verifier").remove("native_oauth_state").apply()
    }

    private fun boundedBody(response: Response): String {
        val source = response.body?.source() ?: return "{}"
        source.request((MAX_API_RESPONSE_BYTES + 1).toLong())
        if (source.buffer.size > MAX_API_RESPONSE_BYTES.toLong()) throw IOException("Vishnu response exceeded the size limit")
        return source.readUtf8()
    }

    private fun apiRequest(method: String, path: String, payload: JSONObject? = null,
                           done: (Boolean, JSONObject?, String) -> Unit) {
        val token = prefs.getString("native_access_token", null)
        if (token.isNullOrBlank() || prefs.getLong("native_expires_at", 0L) <= System.currentTimeMillis()) {
            clearNativeSession()
            runOnUiThread { done(false, null, "Your Vishnu session expired. Sign in again.") }
            return
        }
        val builder = Request.Builder().url(API_BASE + path).header("Authorization", "Bearer $token")
            .header("Accept", "application/json")
        val body = payload?.toString()?.toRequestBody("application/json".toMediaType())
        val request = when (method) {
            "GET" -> builder.get().build()
            "POST" -> builder.post(body ?: "{}".toRequestBody("application/json".toMediaType())).build()
            else -> { runOnUiThread { done(false, null, "Unsupported request method") }; return }
        }
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread { done(false, null, "Vishnu could not complete the request. Check the connection and retry.") }
            }
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val text = try { boundedBody(it) } catch (_: Exception) {
                        runOnUiThread { done(false, null, "Vishnu returned an invalid or oversized response.") }; return
                    }
                    if (it.code == 401) clearNativeSession()
                    val result = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
                    val message = when (it.code) {
                        401 -> "Session expired or revoked. Sign in again."
                        403 -> "This device is not authorized for that action."
                        409 -> "Vishnu requires a fresh owner approval before continuing."
                        in 200..299 -> ""
                        else -> "Vishnu could not complete the request (${it.code})."
                    }
                    runOnUiThread { done(it.isSuccessful, result, message) }
                }
            }
        })
    }

    private fun showCapabilityList(query: String) {
        root.removeAllViews()
        val title = TextView(this).apply { text = "Universal Capabilities"; textSize = 24f; setTextColor(PersonalAITheme.ColorToken.text); setPadding(0, 0, 0, dp(16)) }
        val search = EditText(this).apply { hint = "Search capabilities"; setText(query); imeOptions = EditorInfo.IME_ACTION_SEARCH; inputType = InputType.TYPE_CLASS_TEXT }
        styleField(search)
        val refresh = Button(this).apply { text = "Search and refresh" }
        val importOpenApi = Button(this).apply { text = "Discover OpenAPI document" }
        val addMcp = Button(this).apply { text = "Discover MCP server" }
        val renewSession = Button(this).apply { text = "Rotate native session" }
        val signOut = Button(this).apply { text = "Sign out and revoke this session" }
        listOf(refresh, importOpenApi, addMcp, renewSession, signOut).forEach { styleButton(it, true) }
        (status.parent as? android.view.ViewGroup)?.removeView(status)
        root.addView(title); root.addView(status); root.addView(search); root.addView(refresh); root.addView(importOpenApi); root.addView(addMcp); root.addView(renewSession)
        val results = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(12), 0, dp(20)) }
        root.addView(results); root.addView(signOut)
        refresh.setOnClickListener { showCapabilityList(search.text.toString()) }
        search.setOnEditorActionListener { _, action, _ -> if (action == EditorInfo.IME_ACTION_SEARCH) { showCapabilityList(search.text.toString()); true } else false }
        importOpenApi.setOnClickListener { promptJson("Import OpenAPI document", "Paste the OpenAPI JSON document") { raw ->
            val payload = try { JSONObject().put("document", JSONObject(raw)) } catch (_: Exception) { status.text = "The OpenAPI document must be valid JSON."; return@promptJson }
            reauthenticateThen {
                apiRequest("POST", "/apps-tools/capabilities/openapi", payload) { ok, response, message ->
                    status.text = if (ok) "Discovered ${response?.optInt("discovered", 0) ?: 0} inert operations." else message
                    if (ok) showCapabilityList(search.text.toString())
                }
            }
        } }
        addMcp.setOnClickListener { promptJson("Add MCP server", "Enter {\"name\":\"Server\",\"url\":\"https://…/mcp\"}") { raw ->
            val payload = try { JSONObject(raw) } catch (_: Exception) { status.text = "The MCP descriptor must be valid JSON."; return@promptJson }
            reauthenticateThen {
                apiRequest("POST", "/apps-tools/mcp/servers", payload) { ok, response, message ->
                    val serverId = response?.optJSONObject("server")?.optString("id").orEmpty()
                    status.text = if (ok) "MCP server discovered. Choose its authentication to connect and discover tools." else message
                    if (ok && serverId.isNotBlank()) connectMcpServer(serverId)
                }
            }
        } }
        renewSession.setOnClickListener {
            apiRequest("POST", "/native/sessions/rotate", JSONObject()) { ok, result, message ->
                val replacement = result?.optString("access_token").orEmpty()
                if (!ok || replacement.isBlank()) { status.text = message.ifBlank { "Session rotation failed." }; return@apiRequest }
                val expires = System.currentTimeMillis() + result!!.optLong("expires_in", 0L) * 1000L
                prefs.edit().putString("native_access_token", replacement)
                    .putString("native_session_id", result.optString("session_id"))
                    .putLong("native_expires_at", expires).apply()
                status.text = "Native session rotated securely."
            }
        }
        signOut.setOnClickListener {
            apiRequest("POST", "/native/sessions/logout", JSONObject()) { ok, _, message ->
                clearNativeSession(); status.text = if (ok) "Signed out. Native session revoked." else message
                restoreHome()
            }
        }
        val encoded = URLEncoder.encode(query, "UTF-8")
        status.text = "Loading approved and discovered capabilities…"
        apiRequest("GET", "/apps-tools/capabilities?query=$encoded&limit=100") { ok, response, message ->
            if (!ok) { status.text = message; return@apiRequest }
            val list = response?.optJSONArray("capabilities") ?: JSONArray()
            status.text = if (list.length() == 0) "No matching capabilities. Import an OpenAPI document or add an MCP server." else "${list.length()} capabilities"
            for (i in 0 until list.length()) {
                val item = list.optJSONObject(i) ?: continue
                val button = Button(this).apply {
                    text = "${item.optString("name", "Capability")} · ${item.optString("method", item.optString("type", "tool"))} · ${item.optString("risk", "review")}"
                    contentDescription = "Open details for ${item.optString("name", "capability")}"
                }
                styleButton(button, false)
                button.setOnClickListener { showCapabilityDetail(item.optString("id")) }
                results.addView(button)
            }
        }
    }

    private fun showCapabilityDetail(id: String) {
        if (id.isBlank()) return
        apiRequest("GET", "/apps-tools/capabilities/${Uri.encode(id)}") { ok, response, message ->
            if (!ok) { status.text = message; return@apiRequest }
            val capability = response?.optJSONObject("capability") ?: JSONObject()
            val connection = capability.optJSONObject("connection") ?: JSONObject()
            val connected = connection.optString("status") == "connected"
            val type = capability.optString("type")
            val method = if (type == "mcp_tool" && capability.optString("approved_risk") in setOf("write", "destructive"))
                "POST" else capability.optString("method", "GET").uppercase()
            val builder = AlertDialog.Builder(this).setTitle(capability.optString("name", "Capability"))
                .setMessage("$method · ${capability.optString("risk", "review")}\n${capability.optString("description", capability.optString("summary", ""))}\nConnection: ${connection.optString("status", "not connected")}\nOwner permission checks remain active for every operation.")
                .setNegativeButton("Close", null)
            if (type == "mcp_server") {
                builder.setPositiveButton(if (connected) "Disconnect server" else "Connect and discover tools") { _, _ ->
                    if (connected) reauthenticateThen {
                        apiRequest("POST", "/apps-tools/mcp/servers/${Uri.encode(id)}/disconnect", JSONObject()) { success, _, error ->
                            status.text = if (success) "MCP server and its approved capabilities were disconnected." else error
                            if (success) showCapabilityList("")
                        }
                    } else connectMcpServer(id)
                }
                builder.setNeutralButton("Audit log") { _, _ -> showCapabilityAudit(id, "audit") }
            } else if (type == "mcp_tool") {
                val approvedRisk = capability.optString("approved_risk")
                builder.setPositiveButton(if (approvedRisk.isBlank() || approvedRisk == "null") "Review and approve tool" else "Review risk classification") { _, _ -> reviewMcpTool(id) }
                builder.setNeutralButton("History") { _, _ -> showCapabilityAudit(id, "history") }
            } else if (connected) {
                builder.setPositiveButton("Manage connection") { _, _ ->
                    AlertDialog.Builder(this).setTitle("Connection actions")
                        .setItems(arrayOf("Rotate credential", "Execution history", "Audit log", "Disconnect")) { _, action ->
                            when (action) {
                                0 -> rotateCapabilityCredential(id, type, capability.optString("server_id"))
                                1 -> showCapabilityAudit(id, "history")
                                2 -> showCapabilityAudit(id, "audit")
                                else -> reauthenticateThen {
                                    apiRequest("POST", "/apps-tools/capabilities/${Uri.encode(id)}/disconnect", JSONObject()) { success, _, error ->
                                        status.text = if (success) "Capability disconnected and credential revoked." else error
                                        if (success) showCapabilityList("")
                                    }
                                }
                            }
                        }.setNegativeButton("Cancel", null).show()
                }
                builder.setNeutralButton("Test operation") { _, _ -> promptJson("Test $method capability", "Enter declared operation parameters as JSON") { raw ->
                    val parameters = try { JSONObject(raw.ifBlank { "{}" }) } catch (_: Exception) { status.text = "Parameters must be valid JSON."; return@promptJson }
                    executeCapability(id, method, parameters)
                } }
            } else {
                builder.setPositiveButton("Connect") { _, _ -> chooseCredentialAndConnect(id) }
                builder.setNeutralButton("Audit log") { _, _ -> showCapabilityAudit(id, "audit") }
            }
            builder.show()
        }
    }

    private fun connectMcpServer(id: String) {
        val options = arrayOf("No authentication", "Bearer token", "X-API-Key header")
        AlertDialog.Builder(this).setTitle("Connect MCP server")
            .setItems(options) { _, index ->
                val authType = when (index) { 1 -> "bearer_token"; 2 -> "api_key_header"; else -> "none" }
                val submit: (String) -> Unit = { secret ->
                    val body = JSONObject().put("auth_type", authType)
                    if (secret.isNotEmpty()) body.put("api_key", secret)
                    reauthenticateThen {
                        apiRequest("POST", "/apps-tools/mcp/servers/${Uri.encode(id)}/discover", body) { ok, response, message ->
                            val tools = response?.optJSONArray("tools")?.length() ?: 0
                            status.text = if (ok) "Connected MCP server. Discovered $tools tools; each tool remains inactive until reviewed." else message
                            if (ok) showCapabilityList("")
                        }
                    }
                }
                if (authType == "none") submit("") else {
                    val secretField = EditText(this).apply { hint = "Credential"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD }
                    styleField(secretField)
                    AlertDialog.Builder(this).setTitle("MCP credential")
                        .setView(secretField).setPositiveButton("Connect securely") { _, _ ->
                            val value = secretField.text.toString(); secretField.setText(""); submit(value)
                        }.setNegativeButton("Cancel", null).show()
                }
            }.setNegativeButton("Cancel", null).show()
    }

    private fun reviewMcpTool(id: String) {
        val risks = arrayOf("Read only — I verified the tool cannot write", "Write — may change external data", "Destructive — may delete or irreversibly change data")
        AlertDialog.Builder(this).setTitle("Classify this MCP tool")
            .setMessage("MCP annotations and descriptions do not grant safety. Choose the risk you reviewed.")
            .setItems(risks) { _, index ->
                val risk = when (index) { 0 -> "read"; 1 -> "write"; else -> "destructive" }
                val body = JSONObject().put("risk", risk).put("reviewed", true)
                if (risk == "read") body.put("read_only_attested", true)
                reauthenticateThen {
                    apiRequest("POST", "/apps-tools/mcp/capabilities/${Uri.encode(id)}/approve", body) { ok, _, message ->
                        status.text = if (ok) "MCP tool approved as $risk under Vishnu's permissions." else message
                        if (ok) showCapabilityList("")
                    }
                }
            }.setNegativeButton("Cancel", null).show()
    }

    private fun showCapabilityAudit(id: String, kind: String) {
        apiRequest("GET", "/apps-tools/capabilities/${Uri.encode(id)}/$kind?limit=50") { ok, result, message ->
            if (!ok) { status.text = message; return@apiRequest }
            val entries = result?.optJSONArray("entries") ?: JSONArray()
            val text = if (entries.length() == 0) "No audit entries are available for this capability." else entries.toString(2)
            AlertDialog.Builder(this).setTitle(if (kind == "history") "Execution history" else "Audit log")
                .setMessage(text).setPositiveButton("Close", null).show()
        }
    }

    private fun chooseCredentialAndConnect(id: String) {
        val options = arrayOf("No authentication", "Bearer token", "X-API-Key header")
        AlertDialog.Builder(this).setTitle("Choose secure connection")
            .setItems(options) { _, index ->
                val authType = when (index) { 1 -> "bearer_token"; 2 -> "api_key_header"; else -> "none" }
                if (authType == "none") connectCapability(id, authType, "")
                else {
                    val secret = EditText(this).apply { hint = "Credential"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD }
                    styleField(secret)
                    AlertDialog.Builder(this).setTitle("Enter credential")
                        .setView(secret).setPositiveButton("Approve and connect") { _, _ ->
                            val value = secret.text.toString()
                            secret.setText("")
                            connectCapability(id, authType, value)
                        }.setNegativeButton("Cancel", null).show()
                }
            }.setNegativeButton("Cancel", null).show()
    }

    private fun connectCapability(id: String, authType: String, secret: String) {
        val body = JSONObject().put("auth_type", authType)
        if (secret.isNotEmpty()) body.put("api_key", secret)
        reauthenticateThen {
            apiRequest("POST", "/apps-tools/capabilities/${Uri.encode(id)}/connect", body) { ok, _, message ->
                status.text = if (ok) "Capability approved and connected. Secret remains in Vishnu's vault." else message
                if (ok) showCapabilityDetail(id)
            }
        }
    }

    private fun rotateCapabilityCredential(id: String, type: String, serverId: String) {
        val options = arrayOf("Bearer token", "X-API-Key header")
        AlertDialog.Builder(this).setTitle("Rotate stored credential")
            .setItems(options) { _, index ->
                val authType = if (index == 0) "bearer_token" else "api_key_header"
                val input = EditText(this).apply { hint = "Replacement credential"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD }
                styleField(input)
                AlertDialog.Builder(this).setTitle("Enter replacement credential").setView(input)
                    .setNegativeButton("Cancel", null).setPositiveButton("Rotate securely") { _, _ ->
                        val secret = input.text.toString(); input.setText("")
                        reauthenticateThen {
                            val body = JSONObject().put("auth_type", authType).put("api_key", secret)
                            val route = if (type == "mcp_server" || type == "mcp_tool") {
                                val ownerId = if (type == "mcp_server") id else serverId
                                "/apps-tools/mcp/servers/${Uri.encode(ownerId)}/credentials/rotate"
                            } else "/apps-tools/capabilities/${Uri.encode(id)}/credentials/rotate"
                            apiRequest("POST", route, body) { ok, _, message ->
                                status.text = if (ok) "Credential replaced in Vishnu's vault." else message
                            }
                        }
                    }.show()
            }.setNegativeButton("Cancel", null).show()
    }

    private fun executeCapability(id: String, method: String, parameters: JSONObject) {
        val encodedId = Uri.encode(id)
        val execute = { approvalId: String? ->
            val body = JSONObject().put("parameters", parameters)
            if (!approvalId.isNullOrBlank()) body.put("approval_id", approvalId)
            apiRequest("POST", "/apps-tools/capabilities/$encodedId/execute", body) { ok, response, message ->
                status.text = if (ok) "Operation response: ${response?.optJSONObject("result") ?: response}. Verified: ${response?.optBoolean("verified", false)}" else message
            }
        }
        if (method == "GET") {
            execute(null)
            return
        }
        reauthenticateThen {
            apiRequest("POST", "/apps-tools/capabilities/$encodedId/execution-approvals", JSONObject().put("parameters", parameters)) { created, ticket, message ->
                if (!created) { status.text = message; return@apiRequest }
                val approvalId = ticket?.optString("approval_id").orEmpty()
                AlertDialog.Builder(this).setTitle("Confirm $method operation")
                    .setMessage("This action will be submitted once. Vishnu will not automatically retry it. The provider result may require independent verification.")
                    .setNegativeButton("Cancel", null)
                    .setPositiveButton("Approve once and execute") { _, _ -> reauthenticateThen {
                        apiRequest("POST", "/apps-tools/capabilities/$encodedId/execution-approvals/${Uri.encode(approvalId)}/approve",
                            JSONObject().put("parameters", parameters)) { approved, _, approvalMessage ->
                            if (approved) execute(approvalId) else status.text = approvalMessage
                        }
                    } }.show()
            }
        }
    }

    private fun reauthenticateThen(action: () -> Unit) {
        val password = EditText(this).apply {
            hint = "Vishnu owner password"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        styleField(password)
        AlertDialog.Builder(this).setTitle("Verify owner")
            .setMessage("Sensitive capability changes require recent owner verification.")
            .setView(password).setNegativeButton("Cancel", null)
            .setPositiveButton("Verify") { _, _ ->
                val body = JSONObject().put("password", password.text.toString())
                password.setText("")
                apiRequest("POST", "/native/sessions/reauth", body) { ok, _, message ->
                    if (ok) action() else status.text = message
                }
            }.show()
    }

    private fun promptJson(title: String, hintText: String, submit: (String) -> Unit) {
        val input = EditText(this).apply { hint = hintText; minLines = 5; gravity = android.view.Gravity.TOP; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE }
        styleField(input)
        AlertDialog.Builder(this).setTitle(title).setView(input)
            .setPositiveButton("Continue") { _, _ -> submit(input.text.toString()) }
            .setNegativeButton("Cancel", null).show()
    }

    private fun restoreHome() {
        recreate()
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
