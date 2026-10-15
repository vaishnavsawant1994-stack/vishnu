package ai.personal.companion

import android.app.*
import android.content.*
import android.hardware.camera2.CameraManager
import android.net.Uri
import android.os.*
import androidx.core.app.NotificationCompat
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import okhttp3.*
import org.json.JSONArray
import org.json.JSONObject

class DeviceCommandService: Service() {
  private var ws:WebSocket?=null
  @Volatile private var connecting=false
  private val prefs by lazy { val key=MasterKey.Builder(this).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(); EncryptedSharedPreferences.create(this,"personal_ai_device",key,EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM) }
  private val dataPlane by lazy { MobileDataPlaneStore(applicationContext) }
  private val byteStore by lazy { ManagedByteStore(applicationContext) }
  override fun onCreate(){
    super.onCreate()
    val manager=getSystemService(NotificationManager::class.java)
    manager.createNotificationChannel(NotificationChannel("personal_ai_device","Vishnu Device",NotificationManager.IMPORTANCE_LOW))
    manager.createNotificationChannel(NotificationChannel("vishnu_vision","Vishnu Vision",NotificationManager.IMPORTANCE_HIGH).apply{description="Explicit camera consent requests from your paired Vishnu"})
    startForeground(7,NotificationCompat.Builder(this,"personal_ai_device").setContentTitle("Vishnu connected").setContentText("Secure device command channel active").setSmallIcon(android.R.drawable.stat_notify_sync).build())
    connect()
  }
  override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int{if(ws==null)connect();return START_STICKY}
  override fun onBind(intent:Intent?)=null

  private fun connect(){
    if(connecting || ws!=null)return
    val base=prefs.getString("base",null)?:return
    val serviceId=prefs.getString("service_id",null)
    val pin=prefs.getString("tls_pin",null)
    if(!serviceId.isNullOrBlank() && !pin.isNullOrBlank()){
      connecting=true
      VishnuDiscovery.discover(this,serviceId){result->
        connecting=false
        result.onSuccess{origin->prefs.edit().putString("base",origin).apply();connectTo(origin,pin)}
          .onFailure{connectTo(base,pin)}
      }
      return
    }
    connectTo(base,null)
  }

  private fun connectTo(base:String,pin:String?){
    if(ws!=null)return
    val device=prefs.getString("device",null)?:return
    val bearer=prefs.getString("bearer",null)?:return
    val url=base.replaceFirst("http://","ws://").replaceFirst("https://","wss://").trimEnd('/')+"/device/ws/$device"
    val req=Request.Builder().url(url).addHeader("Authorization","Bearer $bearer").build()
    connecting=true
    ws=PinnedTls.client(pin).newWebSocket(req,object:WebSocketListener(){
      override fun onOpen(w:WebSocket,r:Response){
        connecting=false
        val capabilities=JSONArray(listOf(
          "device_info","battery","flashlight","open_url","launch_app",
          "camera_status","camera_session_start","camera_snapshot","camera_session_stop",
          "data_plane_status","data_plane_progress_put","data_plane_progress_get","data_plane_tombstone",
          "data_plane_progress_pending","data_plane_progress_ack","data_plane_byte_read"
        ))
        w.send(JSONObject().put("type","hello").put("device_id",device).put("platform","android").put("capabilities",capabilities).toString())
      }
      override fun onMessage(w:WebSocket,text:String){handle(w,JSONObject(text))}
      override fun onClosed(w:WebSocket,code:Int,reason:String){ws=null;connecting=false;VisionCameraBridge.deactivate();reconnect()}
      override fun onFailure(w:WebSocket,t:Throwable,r:Response?){ws=null;connecting=false;VisionCameraBridge.deactivate();reconnect()}
    })
  }

  private fun reconnect(){Handler(Looper.getMainLooper()).postDelayed({connect()},3000)}

  private fun requestVisionConsent(facing:String):JSONObject{
    val normalized=if(facing.lowercase()=="back")"back" else "front"
    val intent=Intent(this,VisionCameraActivity::class.java).putExtra("facing",normalized).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    val pending=PendingIntent.getActivity(this,81,intent,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    val notification=NotificationCompat.Builder(this,"vishnu_vision")
      .setSmallIcon(android.R.drawable.ic_menu_camera)
      .setContentTitle("Vishnu wants to use your camera")
      .setContentText("Tap to review and start a 5-minute snapshot-only Vision session.")
      .setContentIntent(pending)
      .setAutoCancel(true)
      .setPriority(NotificationCompat.PRIORITY_HIGH)
      .build()
    getSystemService(NotificationManager::class.java).notify(81,notification)
    val status=VisionCameraBridge.status(this)
    return JSONObject()
      .put("active",status.optBoolean("active",false))
      .put("consent_required",!status.optBoolean("active",false))
      .put("foreground_required",true)
      .put("facing",normalized)
  }

  private fun handle(w:WebSocket,msg:JSONObject){
    if(msg.optString("type")!="command")return
    val id=msg.optString("request_id")
    val action=msg.optString("action")
    val p=msg.optJSONObject("parameters")?:JSONObject()
    try{
      val result=when(action){
        "device_info"->JSONObject().put("manufacturer",Build.MANUFACTURER).put("model",Build.MODEL).put("sdk",Build.VERSION.SDK_INT)
        "battery"->{val bm=getSystemService(BATTERY_SERVICE) as BatteryManager; JSONObject().put("percent",bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY))}
        "flashlight"->{val cm=getSystemService(CameraManager::class.java); val id0=cm.cameraIdList.first(); cm.setTorchMode(id0,p.optBoolean("enabled",true)); JSONObject().put("enabled",p.optBoolean("enabled",true))}
        "open_url"->{val i=Intent(Intent.ACTION_VIEW,Uri.parse(p.getString("url"))).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);startActivity(i);JSONObject().put("opened",true)}
        "launch_app"->{val i=packageManager.getLaunchIntentForPackage(p.getString("package"))?:throw IllegalArgumentException("package not launchable");i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);startActivity(i);JSONObject().put("launched",true)}
        "camera_status"->VisionCameraBridge.status(this)
        "camera_session_start"->requestVisionConsent(p.optString("facing","front"))
        "camera_snapshot"->VisionCameraBridge.snapshot(this)
        "camera_session_stop"->{VisionCameraBridge.deactivate();getSystemService(NotificationManager::class.java).cancel(81);JSONObject().put("stopped",true)}
        "data_plane_status"->dataPlane.status()
        "data_plane_progress_put"->dataPlane.putProgress(
          p.getString("global_id"),
          p.optString("entity_type","project"),
          p.getLong("version"),
          p.optJSONObject("payload")?:JSONObject()
        )
        "data_plane_progress_get"->dataPlane.get(p.getString("global_id"))?:JSONObject().put("missing",true)
        "data_plane_tombstone"->JSONObject().put("deleted",dataPlane.tombstone(p.getString("global_id"),p.getLong("version")))
        "data_plane_progress_pending"->dataPlane.pending(p.optInt("limit",100))
        "data_plane_progress_ack"->JSONObject().put("acknowledged",dataPlane.acknowledge(p.getString("source_event_id")))
        "data_plane_byte_read"->{
          val sessionId=p.getString("session_id")
          val leaseId=p.getString("lease_id")
          require(sessionId.length in 8..200 && leaseId.length in 8..200){"valid lease-bound session identity is required"}
          byteStore.readChunk(
            p.getString("global_id"),p.getLong("object_version"),p.getLong("offset"),p.getInt("length")
          )
        }
        else->throw IllegalArgumentException("unsupported action")
      }
      w.send(JSONObject().put("type","result").put("request_id",id).put("ok",true).put("result",result).toString())
    }catch(e:Exception){
      w.send(JSONObject().put("type","result").put("request_id",id).put("ok",false).put("error",e.message).toString())
    }
  }

  override fun onDestroy(){ws?.close(1000,"service stopping");ws=null;VisionCameraBridge.deactivate();dataPlane.close();super.onDestroy()}
}
