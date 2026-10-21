package ai.personal.companion

import android.content.Intent
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.InputType
import android.util.Base64
import android.view.View
import android.view.Gravity
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Spinner
import android.widget.ScrollView
import android.widget.TextView
import android.widget.ArrayAdapter
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
import java.security.SecureRandom
import java.util.UUID

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
    private lateinit var createBox: LinearLayout
    private lateinit var createStatus: TextView
    private lateinit var recoveryCodes: TextView
    private lateinit var recoverySaved: CheckBox
    private lateinit var modelProvider: Spinner
    private lateinit var modelName: EditText
    private lateinit var providerKey: EditText
    private lateinit var privacyChoice: Spinner
    private lateinit var dataPolicyChoice: Spinner
    private lateinit var authenticationChoice: Spinner
    private lateinit var firstName: EditText
    private lateinit var lastName: EditText
    private lateinit var displayName: EditText
    private lateinit var firstDeviceName: EditText
    private lateinit var bootstrap: EditText
    private lateinit var ownerPassword: EditText
    private lateinit var ownerPasswordAgain: EditText
    private lateinit var createButton: Button
    private lateinit var finishButton: Button
    private lateinit var firstRunBase: EditText
    private lateinit var restoreBox: LinearLayout
    private lateinit var restoreBase: EditText
    private lateinit var recoveryCodeInput: EditText
    private lateinit var restoreStatus: TextView
    private var genesisStep = 1
    private lateinit var genesisProgress: TextView
    private lateinit var genesisHeading: TextView
    private lateinit var genesisSubtitle: TextView

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
            background = BitmapDrawable(resources, BitmapFactory.decodeResource(resources, R.drawable.vishnu_genesis_cosmic_mobile)).apply {
                gravity = Gravity.FILL
            }
        }
        val brand = TextView(this).apply {
            text = "V I S H N U"
            textSize = 22f
            gravity = android.view.Gravity.CENTER
            letterSpacing = .28f
            setTextColor(PersonalAITheme.ColorToken.text)
        }
        val core = VishnuGenesisCoreView(this)
        val title = TextView(this).apply {
            text = "Welcome to Vishnu"
            textSize = 30f
            gravity = android.view.Gravity.CENTER
            setTextColor(PersonalAITheme.ColorToken.text)
            setPadding(0, dp(18), 0, dp(10))
        }
        val copy = TextView(this).apply {
            text = "Your personal intelligence. Your data. Your world."
            textSize = 15f
            gravity = android.view.Gravity.CENTER
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, 0, 0, dp(24))
        }
        val create = Button(this).apply { text = "Create my Vishnu" }
        styleButton(create, true)
        val join = Button(this).apply {
            text = "I already have Vishnu"
            contentDescription = "Connect this Android device to your existing Vishnu by scanning its one-time QR code"
        }
        styleButton(join, false)
        val restore = Button(this).apply { text = "Restore Vishnu" }
        styleButton(restore, false)

        val scan = Button(this).apply { text = "Scan Vishnu QR" }
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

        val joinCopy = TextView(this).apply {
            text = "Scan the one-time QR shown by your existing Vishnu. It finds the runtime on your local network and verifies its TLS identity before sending any pairing secret."
            textSize = 14f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(12), 0, dp(12))
            visibility = View.GONE
        }
        scan.visibility = View.GONE
        manual.visibility = View.GONE
        manualBox.visibility = View.GONE
        val joinBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(joinCopy)
            addView(scan)
            addView(manual)
            addView(manualBox)
        }
        join.setOnClickListener {
            joinBox.visibility = if (joinBox.visibility == View.VISIBLE) View.GONE else View.VISIBLE
            joinCopy.visibility = joinBox.visibility
            scan.visibility = joinBox.visibility
            manual.visibility = joinBox.visibility
        }

        createBox = buildFirstRunForm()
        createBox.visibility = if (prefs.getString("pending_recovery_codes", null).isNullOrBlank()) View.GONE else View.VISIBLE
        restoreBox = buildRestoreForm()
        restoreBox.visibility = View.GONE
        val welcomeGroup = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            addView(title)
            addView(copy)
            addView(create)
            addView(join)
            addView(restore)
        }
        val backToWelcome = Button(this).apply { text = "Back to Welcome"; visibility = View.GONE }
        styleButton(backToWelcome, false)
        backToWelcome.setOnClickListener {
            if (createBox.visibility == View.VISIBLE && genesisStep > 2 && prefs.getString("pending_recovery_codes", null).isNullOrBlank()) {
                genesisStep -= 1
                renderGenesisStep()
                return@setOnClickListener
            }
            createBox.visibility = View.GONE
            restoreBox.visibility = View.GONE
            joinBox.visibility = View.GONE
            welcomeGroup.visibility = View.VISIBLE
            backToWelcome.visibility = View.GONE
        }
        create.setOnClickListener {
            createBox.visibility = View.VISIBLE
            restoreBox.visibility = View.GONE
            joinBox.visibility = View.GONE
            welcomeGroup.visibility = View.GONE
            backToWelcome.text = "Back"
            backToWelcome.visibility = View.VISIBLE
            genesisStep = if (prefs.getString("pending_recovery_codes", null).isNullOrBlank()) 2 else 4
            renderGenesisStep()
        }
        join.setOnClickListener {
            welcomeGroup.visibility = View.GONE
            createBox.visibility = View.GONE
            restoreBox.visibility = View.GONE
            joinBox.visibility = View.VISIBLE
            joinCopy.visibility = View.VISIBLE
            scan.visibility = View.VISIBLE
            manual.visibility = View.VISIBLE
            backToWelcome.visibility = View.VISIBLE
            backToWelcome.text = "Back to Welcome"
        }
        restore.setOnClickListener {
            restoreBox.visibility = View.VISIBLE
            createBox.visibility = View.GONE
            joinBox.visibility = View.GONE
            welcomeGroup.visibility = View.GONE
            backToWelcome.visibility = View.VISIBLE
            backToWelcome.text = "Back to Welcome"
        }
        if (!prefs.getString("pending_recovery_codes", null).isNullOrBlank()) {
            welcomeGroup.visibility = View.GONE
            backToWelcome.visibility = View.VISIBLE
            backToWelcome.text = "Back"
            genesisStep = 4
            renderGenesisStep()
        }

        status = TextView(this).apply {
            text = ""
            textSize = 13f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(20), 0, 0)
        }
        val safety = TextView(this).apply {
            text = "Privacy     |     Accessibility"
            textSize = 12f
            gravity = Gravity.CENTER
            setTextColor(PersonalAITheme.ColorToken.mutedText)
            setPadding(0, dp(20), 0, 0)
        }

        root.addView(brand)
        val wordmarkLine = View(this).apply {
            background = GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                intArrayOf(Color.TRANSPARENT, PersonalAITheme.ColorToken.brightAccent, Color.TRANSPARENT),
            )
        }
        root.addView(wordmarkLine, LinearLayout.LayoutParams(dp(175), dp(1)).apply {
            gravity = Gravity.CENTER
            topMargin = dp(12)
            bottomMargin = dp(10)
        })
        root.addView(core, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(220)))
        root.addView(welcomeGroup)
        root.addView(backToWelcome)
        root.addView(createBox)
        root.addView(restoreBox)
        root.addView(joinBox)
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

    private fun buildFirstRunForm(): LinearLayout {
        val form = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(18), 0, dp(10))
        }
        genesisProgress = TextView(this).apply { gravity = android.view.Gravity.CENTER; textSize = 12f; setTextColor(PersonalAITheme.ColorToken.brightAccent); tag = "genesis-common" }
        genesisHeading = TextView(this).apply { gravity = android.view.Gravity.CENTER; textSize = 30f; setTextColor(PersonalAITheme.ColorToken.text); setPadding(0, dp(14), 0, dp(6)); tag = "genesis-common" }
        genesisSubtitle = TextView(this).apply { gravity = android.view.Gravity.CENTER; textSize = 15f; setTextColor(PersonalAITheme.ColorToken.secondaryText); setPadding(0, 0, 0, dp(16)); tag = "genesis-common" }
        val explanation = TextView(this).apply {
            text = "Owner identity, security, recovery, and trusted-device creation are completed by your local Vishnu runtime."
            textSize = 13f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, 0, 0, dp(12))
            tag = "genesis-3"
        }
        firstRunBase = EditText(this).apply {
            hint = "Secure Vishnu runtime URL (https://…)"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setText(prefs.getString("base", "") ?: "")
            tag = "genesis-3"
        }
        bootstrap = EditText(this).apply {
            hint = "One-time runtime setup code"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            tag = "genesis-3"
        }
        firstName = EditText(this).apply { hint = "First name"; tag = "genesis-2" }
        lastName = EditText(this).apply { hint = "Last name"; tag = "genesis-2" }
        displayName = EditText(this).apply { hint = "Display name (optional)"; tag = "genesis-2" }
        firstDeviceName = EditText(this).apply {
            hint = "Name this device"; setText(android.os.Build.MODEL.take(120)); tag = "genesis-3"
        }
        ownerPassword = EditText(this).apply {
            hint = "Owner password (12 characters minimum)"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            tag = "genesis-3"
        }
        ownerPasswordAgain = EditText(this).apply {
            hint = "Confirm owner password"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            tag = "genesis-3"
        }
        listOf(firstRunBase, bootstrap, firstName, lastName, displayName, ownerPassword, ownerPasswordAgain, firstDeviceName)
            .forEach(::styleField)
        val securityNote = TextView(this).apply {
            text = "This first-device ceremony starts with your owner password and one-time recovery codes. After setup, use Protect Vishnu with a passkey when this runtime publishes the signed Android app association."
            textSize = 12f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(4), 0, dp(10))
            tag = "genesis-3"
        }
        createButton = Button(this).apply { text = "Create owner security →"; tag = "genesis-3" }
        styleButton(createButton, true)
        createStatus = TextView(this).apply {
            textSize = 13f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(8), 0, dp(10))
        }
        recoveryCodes = TextView(this).apply {
            textSize = 14f
            setTextIsSelectable(true)
            setTextColor(PersonalAITheme.ColorToken.text)
            background = rounded(PersonalAITheme.ColorToken.surface, PersonalAITheme.ColorToken.border)
            setPadding(dp(14), dp(14), dp(14), dp(14))
            tag = "genesis-4"
        }
        recoverySaved = CheckBox(this).apply {
            text = "I saved these recovery codes somewhere outside this phone."
            setTextColor(PersonalAITheme.ColorToken.text)
            tag = "genesis-4"
        }
        val privacyLabel = TextView(this).apply {
            text = "Where may Vishnu use your data?"
            textSize = 13f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(14), 0, dp(5))
            tag = "genesis-9"
        }
        privacyChoice = Spinner(this).apply {
            adapter = ArrayAdapter(this@ConnectActivity,
                android.R.layout.simple_spinner_dropdown_item,
                listOf("Local only", "Local preferred", "External providers allowed"))
            tag = "genesis-9"
        }
        authenticationChoice = Spinner(this).apply {
            adapter = ArrayAdapter(this@ConnectActivity, android.R.layout.simple_spinner_dropdown_item,
                listOf("Passkey — Recommended", "Password", "Passkey + Password"))
            tag = "genesis-3"
        }
        dataPolicyChoice = Spinner(this).apply {
            adapter = ArrayAdapter(this@ConnectActivity, android.R.layout.simple_spinner_dropdown_item,
                listOf("Device Only", "Progress Only — Recommended", "Sync Everywhere", "On Demand"))
            setSelection(0)
            tag = "genesis-7"
        }
        modelProvider = Spinner(this).apply {
            adapter = ArrayAdapter(this@ConnectActivity,
                android.R.layout.simple_spinner_dropdown_item,
                listOf("Configure later", "Use a local model", "OpenAI", "Gemini", "OpenRouter", "DeepSeek", "xAI", "Groq", "Cerebras", "Mistral", "Custom provider"))
            tag = "genesis-8"
        }
        modelName = EditText(this).apply { hint = "Provider model name"; tag = "genesis-8" }
        providerKey = EditText(this).apply {
            hint = "Provider API key"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            tag = "genesis-8"
        }
        listOf(modelName, providerKey).forEach(::styleField)
        modelName.visibility = View.GONE
        providerKey.visibility = View.GONE
        modelProvider.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                val needsCredentials = position >= 2
                modelName.visibility = if (needsCredentials) View.VISIBLE else View.GONE
                providerKey.visibility = if (needsCredentials) View.VISIBLE else View.GONE
            }
        }
        finishButton = Button(this).apply {
            text = "Create my Vishnu →"
            tag = "genesis-4"
        }
        styleButton(finishButton, true)
        fun stepButton(step: Int, label: String, next: () -> Unit) = Button(this).apply {
            text = "$label →"; tag = "genesis-$step"; styleButton(this, true); setOnClickListener { next() }
        }
        val identityNext = stepButton(2, "Continue") {
            if (firstName.text.toString().trim().isEmpty()) createStatus.text = "First name is required."
            else { genesisStep = 3; renderGenesisStep() }
        }
        val securityNext = stepButton(3, "Continue") { genesisStep = 4; renderGenesisStep() }
        val recoveryNext = stepButton(5, "Continue") {
            if (!recoverySaved.isChecked) createStatus.text = "Confirm that you safely stored the recovery codes."
            else { genesisStep = 6; renderGenesisStep() }
        }
        val deviceSummary = TextView(this).apply {
            text = "This Android device\nSecure device credential created\nCan be revoked later"
            textSize = 15f; setTextColor(PersonalAITheme.ColorToken.text); setPadding(dp(16), dp(16), dp(16), dp(16))
            background = rounded(PersonalAITheme.ColorToken.surface, PersonalAITheme.ColorToken.border); tag = "genesis-6"
        }
        val deviceNext = stepButton(6, "Trust this device") { genesisStep = 7; renderGenesisStep() }
        val dataNext = stepButton(7, "Continue") { genesisStep = 8; renderGenesisStep() }
        val modelNext = stepButton(8, "Continue") { genesisStep = 9; renderGenesisStep() }
        val privacyNext = stepButton(9, "Continue") { genesisStep = 10; renderGenesisStep() }
        val reviewSummary = TextView(this).apply {
            text = "QUICK REVIEW\nOwner security: password\nFirst device: independently trusted\nData: device only on the selected runtime\nAI provider: configure later\nPrivacy: local only by default"
            textSize = 15f; setTextColor(PersonalAITheme.ColorToken.text); setPadding(dp(16), dp(16), dp(16), dp(16))
            background = rounded(PersonalAITheme.ColorToken.surface, PersonalAITheme.ColorToken.border); tag = "genesis-4"
        }
        form.addView(genesisProgress)
        form.addView(genesisHeading)
        form.addView(genesisSubtitle)
        form.addView(explanation)
        form.addView(firstName)
        form.addView(lastName)
        form.addView(displayName)
        form.addView(identityNext)
        form.addView(firstRunBase)
        form.addView(bootstrap)
        form.addView(ownerPassword)
        form.addView(ownerPasswordAgain)
        form.addView(firstDeviceName)
        form.addView(securityNote)
        form.addView(createButton)
        form.addView(createStatus)
        form.addView(recoveryCodes)
        form.addView(recoverySaved)
        form.addView(reviewSummary)
        form.addView(finishButton)

        createButton.setOnClickListener { createNativeFirstRun() }
        finishButton.setOnClickListener { completeNativeFirstRun() }
        prefs.getString("pending_recovery_codes", null)?.let { saved ->
            runCatching { org.json.JSONArray(saved) }.getOrNull()?.let { codes ->
                if (codes.length() >= 4) {
                    recoveryCodes.text = "Save these one-time codes somewhere outside this phone. They are shown only during setup.\n\n" +
                        (0 until codes.length()).joinToString("\n") { codes.optString(it) }
                    genesisStep = 4
                    createStatus.text = "Resume setup by confirming you saved the recovery codes."
                }
            }
        }
        renderGenesisStep(form)
        return form
    }

    private fun renderGenesisStep(container: LinearLayout = createBox) {
        val titles = mapOf(
            2 to ("What should Vishnu call you?" to "Tell Vishnu your name. Personalize later."),
            3 to ("Secure Your Vishnu" to "Create a password and name your first device."),
            4 to ("Save Your Recovery Codes" to "One-time access recovery codes are not a data backup."),
        )
        genesisProgress.text = "Create Vishnu · Step $genesisStep of 4\n" + (1..4).joinToString(" ") { if (it <= genesisStep) "●" else "○" }
        genesisHeading.text = titles[genesisStep]?.first.orEmpty()
        genesisSubtitle.text = titles[genesisStep]?.second.orEmpty()
        for (index in 0 until container.childCount) {
            val child = container.getChildAt(index)
            val marker = child.tag as? String ?: continue
            if (marker.startsWith("genesis-")) child.visibility = if (marker == "genesis-common" || marker == "genesis-$genesisStep") View.VISIBLE else View.GONE
        }
        if (genesisStep == 8) {
            val needsCredentials = modelProvider.selectedItemPosition >= 2
            modelName.visibility = if (needsCredentials) View.VISIBLE else View.GONE
            providerKey.visibility = if (needsCredentials) View.VISIBLE else View.GONE
        }
        createStatus.text = ""
    }

    private fun buildRestoreForm(): LinearLayout {
        val form = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(18), 0, dp(10))
        }
        val explanation = TextView(this).apply {
            text = "Use a recovery code to add this phone to the secure Vishnu runtime that owns your identity. If that runtime was lost, restore its owner-controlled backup first."
            textSize = 13f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, 0, 0, dp(10))
        }
        restoreBase = EditText(this).apply {
            hint = "Secure Vishnu runtime URL (https://…)"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setText(prefs.getString("base", "") ?: "")
        }
        recoveryCodeInput = EditText(this).apply {
            hint = "One-time recovery code"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        styleField(restoreBase)
        styleField(recoveryCodeInput)
        val restoreButton = Button(this).apply { text = "Restore Vishnu on this phone" }
        styleButton(restoreButton, true)
        restoreStatus = TextView(this).apply {
            textSize = 13f
            setTextColor(PersonalAITheme.ColorToken.secondaryText)
            setPadding(0, dp(8), 0, dp(10))
        }
        form.addView(explanation)
        form.addView(restoreBase)
        form.addView(recoveryCodeInput)
        form.addView(restoreButton)
        form.addView(restoreStatus)
        restoreButton.setOnClickListener { restoreNativeDevice(restoreButton) }
        return form
    }

    private fun restoreNativeDevice(button: Button) {
        try {
            val origin = PairingPayloadParser.normalizeOrigin(restoreBase.text.toString(), false)
            if (!origin.startsWith("https://")) throw IllegalArgumentException("Use a secure HTTPS Vishnu runtime URL.")
            val recovery = recoveryCodeInput.text.toString().trim()
            if (recovery.length < 8) throw IllegalArgumentException("Enter one of your saved recovery codes.")
            val deviceId = prefs.getString("pending_restore_device", null) ?: UUID.randomUUID().toString()
            val deviceToken = prefs.getString("pending_restore_bearer", null) ?: secureRandomText()
            prefs.edit().putString("pending_restore_device", deviceId)
                .putString("pending_restore_bearer", deviceToken).putString("pending_restore_base", origin).apply()
            val payload = JSONObject()
                .put("recovery_code", recovery)
                .put("device_id", deviceId)
                .put("device_token", deviceToken)
                .put("device_name", firstDeviceName.text.toString().trim().take(120))
                .put("platform", "android")
            button.isEnabled = false
            restoreStatus.text = "Verifying recovery and trusting this phone…"
            val request = Request.Builder().url("${origin.trimEnd('/')}/iphone/api/access/native/recovery")
                .post(payload.toString().toRequestBody("application/json".toMediaType()))
                .header("Accept", "application/json").build()
            PinnedTls.client(null).newCall(request).enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) = runOnUiThread {
                    button.isEnabled = true
                    restoreStatus.text = "Could not reach Vishnu. Check the secure address and retry."
                }
                override fun onResponse(call: Call, response: Response) {
                    response.use {
                        val raw = try { boundedBody(it) } catch (_: Exception) { "" }
                        runOnUiThread {
                            button.isEnabled = true
                            if (!it.isSuccessful) {
                                restoreStatus.text = if (it.code == 401) "That recovery code is invalid or already used." else "Vishnu could not restore this phone (${it.code}). Check the runtime and retry."
                                return@runOnUiThread
                            }
                            val result = try { JSONObject(raw) } catch (_: Exception) { null }
                            if (result?.optString("status") != "ready") {
                                restoreStatus.text = "Vishnu did not confirm the device restore. Retry safely."
                                return@runOnUiThread
                            }
                            prefs.edit().putString("base", origin).putString("device", deviceId)
                                .putString("bearer", deviceToken).remove("pending_restore_device")
                                .remove("pending_restore_bearer").remove("pending_restore_base").apply()
                            recoveryCodeInput.setText("")
                            openVishnu()
                        }
                    }
                }
            })
        } catch (exc: IllegalArgumentException) {
            restoreStatus.text = exc.message ?: "Check the recovery details and try again."
        }
    }

    private fun createNativeFirstRun() {
        try {
            val origin = PairingPayloadParser.normalizeOrigin(firstRunBase.text.toString(), false)
            if (!origin.startsWith("https://")) throw IllegalArgumentException("Use a secure HTTPS Vishnu runtime URL.")
            val first = firstName.text.toString().trim()
            val password = ownerPassword.text.toString()
            if (first.isBlank()) throw IllegalArgumentException("Enter your first name.")
            if (firstDeviceName.text.toString().trim().isBlank()) throw IllegalArgumentException("Name this device.")
            if (password.length < 12) throw IllegalArgumentException("Use an owner password with at least 12 characters.")
            if (password != ownerPasswordAgain.text.toString()) throw IllegalArgumentException("The passwords did not match.")
            if (bootstrap.text.toString().length < 32) throw IllegalArgumentException("Enter the one-time setup code provided for this runtime.")
            val setupClaim = prefs.getString("pending_setup_claim", null) ?: secureRandomText()
            val deviceId = prefs.getString("pending_device", null) ?: UUID.randomUUID().toString()
            val deviceToken = prefs.getString("pending_bearer", null) ?: secureRandomText()
            prefs.edit().putString("pending_setup_claim", setupClaim).putString("pending_device", deviceId)
                .putString("pending_bearer", deviceToken).putString("pending_base", origin).apply()
            createButton.isEnabled = false
            createStatus.text = "Creating your owner identity and first trusted device…"
            val payload = JSONObject()
                .put("bootstrap_secret", bootstrap.text.toString())
                .put("setup_claim", setupClaim)
                .put("first_name", first)
                .put("last_name", lastName.text.toString().trim())
                .put("display_name", displayName.text.toString().trim())
                .put("password", password)
                .put("device_id", deviceId)
                .put("device_token", deviceToken)
                .put("device_name", android.os.Build.MODEL.take(120))
                .put("platform", "android")
            val request = Request.Builder().url("${origin.trimEnd('/')}/iphone/api/first-run/native/create")
                .post(payload.toString().toRequestBody("application/json".toMediaType()))
                .header("Accept", "application/json").build()
            PinnedTls.client(null).newCall(request).enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) = runOnUiThread {
                    createButton.isEnabled = true
                    createStatus.text = "Could not reach that secure runtime. Check the address and network, then retry."
                }
                override fun onResponse(call: Call, response: Response) {
                    response.use {
                        val raw = try { boundedBody(it) } catch (_: Exception) { "" }
                        runOnUiThread {
                            createButton.isEnabled = true
                            if (!it.isSuccessful) {
                                createStatus.text = if (it.code == 409) "Vishnu is already initialized or another setup is in progress. Connect this phone to the existing Vishnu." else "Vishnu setup could not continue (${it.code}). Check the runtime setup code and try again."
                                return@runOnUiThread
                            }
                            val result = try { JSONObject(raw) } catch (_: Exception) { null }
                            if (result == null) {
                                createStatus.text = "The runtime returned an invalid setup response. Retry safely to continue."
                                return@runOnUiThread
                            }
                            if (result.optString("status") == "ready") {
                                activatePendingDevice()
                                openVishnu()
                                return@runOnUiThread
                            }
                            val codes = result.optJSONArray("recovery_codes")
                            if (codes == null || codes.length() < 4) {
                                createStatus.text = "The runtime did not return the recovery codes. Retry setup to generate a fresh set."
                                return@runOnUiThread
                            }
                            val text = (0 until codes.length()).joinToString("\n") { index -> codes.optString(index) }
                            prefs.edit().putString("pending_recovery_codes", codes.toString()).apply()
                            recoveryCodes.text = "Save these one-time codes somewhere outside this phone. They are shown here only during setup.\n\n$text"
                            genesisStep = 4
                            renderGenesisStep()
                            createStatus.text = "Your identity and first trusted device are ready. Save recovery codes before continuing."
                            bootstrap.setText("")
                            ownerPassword.setText("")
                            ownerPasswordAgain.setText("")
                        }
                    }
                }
            })
        } catch (exc: IllegalArgumentException) {
            createStatus.text = exc.message ?: "Check the setup details and try again."
        }
    }

    private fun completeNativeFirstRun() {
        if (!recoverySaved.isChecked) {
            createStatus.text = "Confirm that you saved your recovery codes before continuing."
            return
        }
        val origin = prefs.getString("pending_base", null) ?: return
        val providers = listOf("skip", "local", "openai", "gemini", "openrouter", "deepseek", "xai", "groq", "cerebras", "mistral", "custom")
        val provider = providers.getOrElse(modelProvider.selectedItemPosition) { "skip" }
        if (provider !in setOf("skip", "local")) {
            if (modelName.text.toString().trim().isEmpty()) {
                createStatus.text = "Enter the model name for the selected provider."
                return
            }
            if (providerKey.text.toString().length < 16) {
                createStatus.text = "Enter the provider API key, or choose Configure later."
                return
            }
        }
        val credentials = JSONObject()
            .put("setup_claim", prefs.getString("pending_setup_claim", ""))
            .put("device_id", prefs.getString("pending_device", ""))
            .put("device_token", prefs.getString("pending_bearer", ""))
            .put("provider_id", provider)
            .put("model", modelName.text.toString().trim())
            .put("api_key", providerKey.text.toString())
        finishButton.isEnabled = false
        createStatus.text = "Saving your AI choice securely…"
        val modelRequest = Request.Builder().url("${origin.trimEnd('/')}/iphone/api/first-run/native/model")
            .post(credentials.toString().toRequestBody("application/json".toMediaType()))
            .header("Accept", "application/json").build()
        PinnedTls.client(null).newCall(modelRequest).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) = runOnUiThread {
                finishButton.isEnabled = true
                createStatus.text = "Could not reach Vishnu. Your setup is saved; reconnect and finish again."
            }
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val raw = try { boundedBody(it) } catch (_: Exception) { "" }
                    runOnUiThread {
                        val result = try { JSONObject(raw) } catch (_: Exception) { null }
                        if (!it.isSuccessful || result?.optBoolean("ok") != true) {
                            finishButton.isEnabled = true
                            createStatus.text = "Vishnu could not save that AI choice (${it.code}). Check the choice and retry."
                            return@runOnUiThread
                        }
                        providerKey.setText("")
                        completeNativeSetup(origin, provider != "skip")
                    }
                }
            }
        })
    }

    private fun completeNativeSetup(origin: String, modelConfigured: Boolean) {
        val payload = JSONObject()
            .put("setup_claim", prefs.getString("pending_setup_claim", ""))
            .put("device_id", prefs.getString("pending_device", ""))
            .put("device_token", prefs.getString("pending_bearer", ""))
            .put("recovery_saved", true)
            .put("privacy_mode", listOf("local_only", "local_preferred", "external_allowed").getOrElse(privacyChoice.selectedItemPosition) { "local_only" })
            .put("data_policy", listOf("device_only", "progress_only", "sync_everywhere", "on_demand").getOrElse(dataPolicyChoice.selectedItemPosition) { "progress_only" })
            .put("model_choice", if (modelConfigured) "configured" else "configure_later")
        createStatus.text = "Verifying your recovery and privacy choices…"
        val request = Request.Builder().url("${origin.trimEnd('/')}/iphone/api/first-run/native/complete")
            .post(payload.toString().toRequestBody("application/json".toMediaType()))
            .header("Accept", "application/json").build()
        PinnedTls.client(null).newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) = runOnUiThread {
                finishButton.isEnabled = true
                createStatus.text = "Could not reach Vishnu. Your setup is saved; reconnect and finish again."
            }
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val raw = try { boundedBody(it) } catch (_: Exception) { "" }
                    runOnUiThread {
                        finishButton.isEnabled = true
                        if (!it.isSuccessful) {
                            createStatus.text = "Vishnu setup could not finish (${it.code}). Reconnect and retry."
                            return@runOnUiThread
                        }
                        val result = try { JSONObject(raw) } catch (_: Exception) { null }
                        if (result?.optString("status") != "ready") {
                            createStatus.text = "The runtime did not confirm setup completion. Retry safely."
                            return@runOnUiThread
                        }
                        activatePendingDevice()
                        prefs.edit().remove("pending_recovery_codes").apply()
                        openVishnu()
                    }
                }
            }
        })
    }

    private fun activatePendingDevice() {
        prefs.edit()
            .putString("base", prefs.getString("pending_base", ""))
            .putString("device", prefs.getString("pending_device", ""))
            .putString("bearer", prefs.getString("pending_bearer", ""))
            .remove("pending_base").remove("pending_device").remove("pending_bearer")
            .remove("pending_setup_claim").remove("pending_recovery_codes").apply()
    }

    private fun secureRandomText(): String {
        val bytes = ByteArray(32).also { SecureRandom().nextBytes(it) }
        return Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
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
        val ink = PersonalAITheme.ColorToken.text
        val stroke = if (primary) PersonalAITheme.ColorToken.brightAccent else PersonalAITheme.ColorToken.border
        button.background = rounded(fill, stroke).apply { cornerRadius = dp(28).toFloat() }
        button.backgroundTintList = null
        button.setTextColor(ink)
        button.isAllCaps = false
        button.minHeight = dp(56)
        button.setPadding(dp(20), dp(12), dp(20), dp(12))
        val params = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        params.bottomMargin = dp(10)
        button.layoutParams = params
    }

    private fun rounded(fill: Int, stroke: Int): GradientDrawable = GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        cornerRadius = dp(PersonalAITheme.cornerRadiusDp).toFloat()
        setColor(fill)
        setStroke(dp(1), stroke)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
