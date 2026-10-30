package com.mouya.qbotds

import android.content.Context
import android.util.Log
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject

/**
 * Thin, thread-safe wrapper around the embedded CPython runtime.
 *
 * The heavy lifting lives in `qbot_bridge.py`; this class only starts the
 * interpreter, forwards calls and keeps everything off the UI thread.
 *
 * No part of this touches QQ or its login state. The bot connects outward to
 * an OneBot v11 WebSocket endpoint (see `napcat_ws_url`).
 */
object PythonRuntime {

    private const val TAG = "PythonRuntime"

    private data class FailureDetail(
        val message: String,
        val stackTrace: String,
    )

    @Volatile
    private var startFailure: FailureDetail? = null

    @Volatile
    private var module: PyObject? = null

    private val lock = Any()

    /** True once the interpreter is up and the bridge module imported. */
    val isReady: Boolean
        get() = module != null

    /** Last startup error, or null when healthy. */
    val startupError: String?
        get() = startFailure?.message

    /** Last startup stack trace (for the log panel). */
    val startupTrace: String?
        get() = startFailure?.stackTrace

    /**
     * Start Python and import the bridge. Safe to call repeatedly and from any
     * thread; returns true when the bridge is usable.
     */
    fun ensureStarted(context: Context): Boolean {
        module?.let { return true }

        synchronized(lock) {
            module?.let { return true }

            val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            if (prefs.getBoolean(KEY_CRASHED, false) && startFailure != null) {
                // Previously failed during this install; allow a retry anyway
                // because the cause is often a transient asset problem.
                Log.w(TAG, "retrying after previous start failure")
            }

            return try {
                if (!Python.isStarted()) {
                    // AndroidPlatform puts the app's private files dir on
                    // sys.path and points HOME at it.
                    Python.start(AndroidPlatform(context.applicationContext))
                }

                val python = Python.getInstance()

                // The bridge module reads ANDROID_APP_FILES at import time to
                // decide where the writable bot copy lives, so it must be set
                // before the import below. PyObject exposes dict-style access
                // through callAttr, not getAttr.
                val environ = python.getModule("os").callAttr("__dict__")
                    .callAttr("__getitem__", "environ")
                environ.callAttr("__setitem__", "ANDROID_APP_FILES", context.filesDir.absolutePath)

                module = python.getModule("qbot_bridge")
                startFailure = null
                prefs.edit().putBoolean(KEY_CRASHED, false).apply()
                Log.i(TAG, "python runtime ready")
                true
            } catch (t: Throwable) {
                val detail = FailureDetail(
                    message = t.message ?: t.javaClass.simpleName,
                    stackTrace = Log.getStackTraceString(t),
                )
                startFailure = detail
                module = null
                context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .edit().putBoolean(KEY_CRASHED, true).apply()
                Log.e(TAG, "python startup failed", t)
                false
            }
        }
    }

    private fun bridge(): PyObject? = module

    fun botStatusJson(): JSONObject = callJson("bot_status_json")

    fun safeConfigJson(): JSONObject = callJson("safe_config_json")

    fun readConfigJson(): JSONObject = callJson("read_config_json")

    fun isBotRunning(): Boolean = try {
        bridge()?.callAttr("is_running")?.toBoolean() ?: false
    } catch (t: Throwable) {
        Log.w(TAG, "is_running failed", t)
        false
    }

    fun startBot(): Boolean = try {
        bridge()?.callAttr("run_bot")?.toBoolean() ?: false
    } catch (t: Throwable) {
        Log.e(TAG, "run_bot failed", t)
        false
    }

    fun stopBot(): Boolean = try {
        bridge()?.callAttr("request_stop")?.toBoolean() ?: false
    } catch (t: Throwable) {
        Log.w(TAG, "request_stop failed", t)
        false
    }

    fun writeConfig(payload: String): JSONObject = try {
        val raw = bridge()?.callAttr("write_config_json", payload)?.toString() ?: "{}"
        JSONObject(raw)
    } catch (t: Throwable) {
        Log.w(TAG, "write_config_json failed", t)
        JSONObject().put("ok", false).put("error", t.message ?: "写入失败")
    }

    fun tailLog(lines: Int = 120): String = try {
        bridge()?.callAttr("tail_log", lines)?.toString() ?: ""
    } catch (t: Throwable) {
        Log.w(TAG, "tail_log failed", t)
        ""
    }

    // ── Diagnostics ──────────────────────────────────────────────────────────

    fun testAi(): JSONObject = callNoArg("test_ai_json")

    fun testOneBot(): JSONObject = callNoArg("test_onebot_json")

    fun stats(): JSONObject = callNoArg("stats_json")

    fun clearLog(): JSONObject = callNoArg("clear_log")

    fun personaPreview(length: Int = 400): String = try {
        bridge()?.callAttr("persona_preview", length)?.toString() ?: ""
    } catch (t: Throwable) {
        Log.w(TAG, "persona_preview failed", t)
        ""
    }

    private fun callNoArg(method: String): JSONObject = try {
        val raw = bridge()?.callAttr(method)?.toString()
        if (raw.isNullOrBlank()) JSONObject() else JSONObject(raw)
    } catch (t: Throwable) {
        Log.w(TAG, "$method failed", t)
        JSONObject().put("ok", false).put("detail", t.message ?: "调用失败")
    }

    private fun callJson(method: String): JSONObject = try {
        val raw = bridge()?.callAttr(method)?.toString()
        if (raw.isNullOrBlank()) JSONObject() else JSONObject(raw)
    } catch (t: Throwable) {
        Log.w(TAG, "$method failed", t)
        JSONObject()
    }

    private const val PREFS = "qbot_python_runtime"
    private const val KEY_CRASHED = "crashed"
}