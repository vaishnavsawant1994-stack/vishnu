package ai.personal.companion

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

class SensoriumAudioService : Service() {
    companion object { private const val CHANNEL = "vishnu_sensorium_audio"; private const val NOTIFICATION = 95 }

    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, "Vishnu Environmental Audio", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Visible while Vishnu has an owner-approved environmental microphone session"
            }
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val privacy = PendingIntent.getActivity(
            this,
            9501,
            Intent(this, SensoriumPrivacyActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle("Vishnu can hear environment features")
            .setContentText("Tap for Sensorium Privacy · local features only · temporary session")
            .setContentIntent(privacy)
            .setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(NOTIFICATION, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        else startForeground(NOTIFICATION, notification)
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        SensoriumSessionRegistry.revoke("microphone", "*")
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
