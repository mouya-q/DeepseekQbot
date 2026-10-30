package com.mouya.qbotds

import android.app.Application
import android.util.Log

/**
 * Application entry point.
 *
 * Python startup is deliberately *not* done here: it takes a moment and would
 * slow every cold start. The foreground service owns it instead, so importing
 * the runtime only happens when the user actually starts the bot.
 */
class QbotApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Log.i("QbotApp", "application created")
    }
}