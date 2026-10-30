package com.mouya.qbotds

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlin.concurrent.thread

/**
 * Foreground service that keeps the embedded Python bot alive.
 *
 * The bot must keep running while the user does something else, so Android
 * needs a visible foreground notification. Nothing here interacts with QQ
 * and it does not require root.
 */
class BotService : Service() {

    companion object {
        private const val TAG = "BotService"
        private const val CHANNEL_ID = "qbot_bot"
        private const val NOTIFICATION_ID = 4101

        const val ACTION_START = "com.mouya.qbotds.action.START"
        const val ACTION_STOP = "com.mouya.qbotds.action.STOP"
        const val ACTION_RESTART = "com.mouya.qbotds.action.RESTART"

        /** Broadcast so the UI can refresh without polling. */
        const val EVENT_STATE = "com.mouya.qbotds.event.STATE"

        fun start(context: Context) {
            send(context, ACTION_START)
        }

        fun stop(context: Context) {
            send(context, ACTION_STOP)
        }

        private fun send(context: Context, action: String) {
            val intent = Intent(context, BotService::class.java).setAction(action)
            if (action == ACTION_STOP) {
                context.startService(intent)
            } else {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            }
        }
    }

    private var initializeThread: Thread? = null
    private var failing = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopBotAndSelf()
                return START_NOT_STICKY
            }

            ACTION_RESTART -> {
                PythonRuntime.stopBot()
                launchBot()
                return START_STICKY
            }

            else -> launchBot()
        }
        return START_STICKY
    }

    private fun launchBot() {
        startForeground(NOTIFICATION_ID, buildNotification("正在启动…"))

        if (initializeThread?.isAlive == true) {
            Log.d(TAG, "initialization already in progress")
            return
        }

        initializeThread = thread(name = "qbot-init") {
            val ready = PythonRuntime.ensureStarted(applicationContext)
            if (!ready) {
                failing = true
                val detail = PythonRuntime.startupError ?: "Python 运行时启动失败"
                Log.e(TAG, "runtime start failed: $detail")
                updateNotification("启动失败：$detail")
                broadcastState()
                return@thread
            }

            val started = PythonRuntime.startBot()
            Log.i(TAG, "run_bot -> $started")
            failing = !started
            updateNotification(
                if (started) "大肥鱼在线" else "机器人启动失败"
            )
            broadcastState()
        }
    }

    private fun stopBotAndSelf() {
        try {
            PythonRuntime.stopBot()
        } catch (t: Throwable) {
            Log.w(TAG, "stop failed", t)
        }
        broadcastState()
        stopForegroundCompat()
        stopSelf()
    }

    private fun broadcastState() {
        sendBroadcast(Intent(EVENT_STATE).setPackage(packageName))
    }

    private fun stopForegroundCompat() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return

        val channel = NotificationChannel(
            CHANNEL_ID,
            "大肥鱼运行状态",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "保持豆包鱼机器人在后台运行"
            setShowBadge(false)
            enableVibration(false)
        }
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(text: String): Notification {
        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pending = PendingIntent.getActivity(
            this,
            0,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val stopIntent = PendingIntent.getService(
            this,
            1,
            Intent(this, BotService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("大肥鱼")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_qbot)
            .setContentIntent(pending)
            .addAction(0, "停止", stopIntent)
            .setOngoing(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(NotificationManager::class.java) ?: return
        try {
            manager.notify(NOTIFICATION_ID, buildNotification(text))
        } catch (t: Throwable) {
            Log.w(TAG, "notify failed", t)
        }
    }

    override fun onDestroy() {
        try {
            PythonRuntime.stopBot()
        } catch (t: Throwable) {
            Log.w(TAG, "stop on destroy failed", t)
        }
        super.onDestroy()
    }
}