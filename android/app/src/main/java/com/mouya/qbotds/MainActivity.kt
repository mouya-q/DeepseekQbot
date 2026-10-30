package com.mouya.qbotds

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import org.json.JSONObject
import top.yukonga.miuix.kmp.basic.Button
import top.yukonga.miuix.kmp.basic.NavigationBar
import top.yukonga.miuix.kmp.basic.NavigationBarItem
import top.yukonga.miuix.kmp.basic.Scaffold
import top.yukonga.miuix.kmp.basic.SmallTopAppBar
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.icon.MiuixIcons
import top.yukonga.miuix.kmp.icon.extended.Contacts
import top.yukonga.miuix.kmp.icon.extended.Home
import top.yukonga.miuix.kmp.icon.extended.Link
import top.yukonga.miuix.kmp.icon.extended.Settings
import top.yukonga.miuix.kmp.theme.ColorSchemeMode
import top.yukonga.miuix.kmp.theme.MiuixTheme
import top.yukonga.miuix.kmp.theme.ThemeController

private const val TAG = "MainActivity"

/** Shown on the About page; keep in sync with versionName. */
private const val APP_VERSION = "1.1.0"

private enum class Page(val label: String) {
    HOME("总览"),
    BOT("QQ"),
    CONFIG("配置"),
    ABOUT("关于"),
}

class MainActivity : ComponentActivity() {

    private var botState by mutableStateOf(BotUiState())

    private val notificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            Log.i(TAG, "post notifications granted=$granted")
        }

    private val stateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) = refreshState()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        window.statusBarColor = android.graphics.Color.rgb(244, 246, 251)
        window.navigationBarColor = android.graphics.Color.WHITE
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility =
            android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or
                android.view.View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR

        askForNotificationPermission()
        refreshState()

        setContent {
            val controller = remember { ThemeController(ColorSchemeMode.Light) }
            MiuixTheme(controller = controller) {
                AppScaffold(
                    state = botState,
                    onStart = { BotService.start(this); refreshState() },
                    onStop = { BotService.stop(this); refreshState() },
                    onRefresh = { refreshState() },
                    onReloadRuntime = { reloadRuntime() },
                    onOpenBattery = { openBatterySettings() },
                    onSaveConfig = { payload -> saveConfig(payload) },
                )
            }
        }
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter(BotService.EVENT_STATE)
        ContextCompat.registerReceiver(this, stateReceiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)
        refreshState()
    }

    override fun onStop() {
        try {
            unregisterReceiver(stateReceiver)
        } catch (t: Throwable) {
            Log.w(TAG, "unregister failed", t)
        }
        super.onStop()
    }

    // ── Actions ──────────────────────────────────────────────────────────────

    private fun reloadRuntime() {
        botState = botState.copy(loading = true)
        Thread {
            val ok = PythonRuntime.ensureStarted(applicationContext)
            runOnUiThread {
                botState = botState.copy(
                    loading = false,
                    runtimeReady = ok,
                    runtimeError = PythonRuntime.startupError,
                )
                refreshState()
            }
        }.start()
    }

    private fun saveConfig(payload: JSONObject) {
        Thread {
            if (!PythonRuntime.ensureStarted(applicationContext)) {
                runOnUiThread { botState = botState.copy(message = "运行时未就绪，无法保存") }
                return@Thread
            }
            val result = PythonRuntime.writeConfig(payload.toString())
            val error = result.optString("error").takeIf { it.isNotBlank() }
            runOnUiThread {
                botState = botState.copy(
                    message = if (result.optBoolean("ok")) "已保存" else "保存失败：${error ?: "未知错误"}",
                )
            }
            refreshState()
        }.start()
    }

    private fun refreshState() {
        Thread {
            val ready = PythonRuntime.isReady
            val running = if (ready) PythonRuntime.isBotRunning() else false
            val error = PythonRuntime.startupError
            val logTail = if (ready) PythonRuntime.tailLog(60) else PythonRuntime.startupTrace.orEmpty()
            val config = if (ready) PythonRuntime.safeConfigJson() else null

            runOnUiThread {
                botState = botState.copy(
                    loading = false,
                    runtimeReady = ready,
                    running = running,
                    runtimeError = error,
                    log = logTail,
                    model = config?.optString("model").orEmpty(),
                    apiBase = config?.optString("api_base").orEmpty(),
                    napcatWs = config?.optString("napcat_ws_url").orEmpty(),
                    napcatHttp = config?.optString("napcat_http_url").orEmpty(),
                    apiKeySet = config?.optBoolean("api_key_set", false) ?: false,
                    ownerQq = config?.optString("owner_qq").orEmpty(),
                    botQq = config?.optString("bot_qq").orEmpty(),
                    botNick = config?.optString("bot_nick").orEmpty(),
                    groups = config?.optString("allowed_groups").orEmpty(),
                )
            }
        }.start()
    }

    private fun askForNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        val granted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun openBatterySettings() {
        val powerManager = getSystemService(PowerManager::class.java)
        val ignoring = powerManager?.isIgnoringBatteryOptimizations(packageName) == true
        val intent = if (ignoring) {
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                .setData(Uri.fromParts("package", packageName, null))
        } else {
            @Suppress("BatteryLife")
            Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                .setData(Uri.fromParts("package", packageName, null))
        }
        try {
            startActivity(intent)
        } catch (t: Throwable) {
            Log.w(TAG, "battery settings failed", t)
            startActivity(
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .setData(Uri.fromParts("package", packageName, null)),
            )
        }
    }
}

data class BotUiState(
    val loading: Boolean = false,
    val runtimeReady: Boolean = false,
    val running: Boolean = false,
    val runtimeError: String? = null,
    val log: String = "",
    val message: String = "",
    val model: String = "",
    val apiBase: String = "",
    val napcatWs: String = "",
    val napcatHttp: String = "",
    val apiKeySet: Boolean = false,
    val ownerQq: String = "",
    val botQq: String = "",
    val botNick: String = "",
    val groups: String = "",
)

@Composable
private fun AppScaffold(
    state: BotUiState,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onRefresh: () -> Unit,
    onReloadRuntime: () -> Unit,
    onOpenBattery: () -> Unit,
    onSaveConfig: (JSONObject) -> Unit,
) {
    var page by remember { mutableStateOf(Page.HOME) }

    Scaffold(
        topBar = {
            SmallTopAppBar(
                title = "DeepseekQbot",
                actions = {
                    Text(
                        text = "大肥鱼",
                        modifier = Modifier.padding(end = 16.dp),
                        color = Color(0xFF3478F6),
                        fontSize = 12.sp,
                    )
                },
            )
        },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = page == Page.HOME,
                    onClick = { page = Page.HOME },
                    icon = MiuixIcons.Home,
                    label = Page.HOME.label,
                )
                NavigationBarItem(
                    selected = page == Page.BOT,
                    onClick = { page = Page.BOT },
                    icon = MiuixIcons.Link,
                    label = Page.BOT.label,
                )
                NavigationBarItem(
                    selected = page == Page.CONFIG,
                    onClick = { page = Page.CONFIG },
                    icon = MiuixIcons.Contacts,
                    label = Page.CONFIG.label,
                )
                NavigationBarItem(
                    selected = page == Page.ABOUT,
                    onClick = { page = Page.ABOUT },
                    icon = MiuixIcons.Settings,
                    label = Page.ABOUT.label,
                )
            }
        },
    ) { paddingValues: PaddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .background(Color(0xFFF4F6FB)),
        ) {
            when (page) {
                Page.HOME -> HomePage(state, onStart, onStop, onRefresh, onReloadRuntime)
                Page.BOT -> BotPage(state, onStart, onStop, onRefresh, onOpenBattery)
                Page.CONFIG -> ConfigPage(state, onSaveConfig)
                Page.ABOUT -> AboutPage()
            }
        }
    }
}

@Composable
private fun HomePage(
    state: BotUiState,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onRefresh: () -> Unit,
    onReloadRuntime: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        CardBox {
            Text("本鲸在此。", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Text(
                text = "内置 Python 运行时，不需要 proot，也不需要 Termux。",
                color = Color(0xFF79869A),
                fontSize = 12.sp,
            )
            Spacer(Modifier.height(14.dp))
            StatusRow("Python 运行时", if (state.runtimeReady) "已就绪" else "未启动", state.runtimeReady)
            StatusRow("机器人进程", if (state.running) "运行中" else "已停止", state.running)
            StatusRow("模型", state.model.ifBlank { "未配置" }, state.model.isNotBlank())
            StatusRow("API Key", if (state.apiKeySet) "已保存" else "未填写", state.apiKeySet)

            state.runtimeError?.let { err ->
                Spacer(Modifier.height(10.dp))
                Text("启动失败：$err", color = Color(0xFFC84452), fontSize = 11.sp)
            }
            if (state.message.isNotBlank()) {
                Spacer(Modifier.height(10.dp))
                Text(state.message, color = Color(0xFF178F64), fontSize = 11.sp)
            }

            Spacer(Modifier.height(14.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = if (state.running) onStop else onStart) {
                    Text(if (state.running) "停止机器人" else "启动机器人", color = Color.White)
                }
                Button(onClick = onRefresh) { Text("刷新") }
                Button(onClick = onReloadRuntime) { Text("重载") }
            }
        }

        CardBox {
            Text("运行日志", fontSize = 14.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Text(
                text = state.log.ifBlank { "暂无日志。" },
                color = Color(0xFF5B6779),
                fontSize = 10.sp,
            )
        }
    }
}

@Composable
private fun BotPage(
    state: BotUiState,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onRefresh: () -> Unit,
    onOpenBattery: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        CardBox {
            Text("QQ 接入", fontSize = 16.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Text(
                text = "机器人连接小号的 OneBot 端点，不接触你大号的 QQ 登录状态。",
                color = Color(0xFF79869A),
                fontSize = 12.sp,
            )
            Spacer(Modifier.height(12.dp))
            StatusRow("OneBot WS", state.napcatWs.ifBlank { "未配置" }, state.napcatWs.isNotBlank())
            StatusRow("OneBot HTTP", state.napcatHttp.ifBlank { "未配置" }, state.napcatHttp.isNotBlank())
            StatusRow("机器人 QQ", state.botQq.ifBlank { "未设置" }, state.botQq.isNotBlank())
            StatusRow("主人 QQ", state.ownerQq.ifBlank { "未设置" }, state.ownerQq.isNotBlank())
        }

        CardBox {
            Text("后台保活", fontSize = 14.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Text(
                text = "把本应用加入电池优化白名单，避免被系统清理。",
                color = Color(0xFF79869A),
                fontSize = 12.sp,
            )
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = onOpenBattery) { Text("电池设置") }
                Button(onClick = onRefresh) { Text("刷新") }
            }
        }

        CardBox {
            Text("操作", fontSize = 14.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(10.dp))
            Button(onClick = if (state.running) onStop else onStart) {
                Text(if (state.running) "停止" else "启动", color = Color.White)
            }
        }
    }
}

@Composable
private fun ConfigPage(state: BotUiState, onSaveConfig: (JSONObject) -> Unit) {
    var apiBase by remember(state.apiBase) { mutableStateOf(state.apiBase) }
    var apiKey by remember { mutableStateOf("") }
    var model by remember(state.model) { mutableStateOf(state.model) }
    var wsUrl by remember(state.napcatWs) { mutableStateOf(state.napcatWs) }
    var httpUrl by remember(state.napcatHttp) { mutableStateOf(state.napcatHttp) }
    var botQq by remember(state.botQq) { mutableStateOf(state.botQq) }
    var ownerQq by remember(state.ownerQq) { mutableStateOf(state.ownerQq) }
    var botNick by remember(state.botNick) { mutableStateOf(state.botNick) }
    var groups by remember(state.groups) { mutableStateOf(state.groups) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        CardBox {
            Text("模型接口", fontSize = 16.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(12.dp))

            Field("API Base", apiBase, { apiBase = it }, "https://api.example.com/v1")
            Field("API Key", apiKey, { apiKey = it }, if (state.apiKeySet) "已保存，留空则不修改" else "粘贴密钥")
            Field("模型 ID", model, { model = it }, "deepseek-chat")
        }

        CardBox {
            Text("QQ 连接", fontSize = 16.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(12.dp))

            Field("OneBot WS 地址", wsUrl, { wsUrl = it }, "ws://127.0.0.1:3001")
            Field("OneBot HTTP 地址", httpUrl, { httpUrl = it }, "http://127.0.0.1:3000")
            Field("机器人 QQ", botQq, { botQq = it }, "小号 QQ 号", KeyboardType.Number)
            Field("主人 QQ", ownerQq, { ownerQq = it }, "你的大号 QQ 号", KeyboardType.Number)
        }

        CardBox {
            Text("群与昵称", fontSize = 16.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(12.dp))

            Field("机器人昵称", botNick, { botNick = it }, "大肥鱼")
            Field("允许的群号", groups, { groups = it }, "多个群用逗号分隔")

            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = {
                        val payload = JSONObject().apply {
                            put("api_base", apiBase)
                            put("model", model)
                            put("napcat_ws_url", wsUrl)
                            put("napcat_http_url", httpUrl)
                            if (botQq.isNotBlank()) put("bot_qq", botQq)
                            if (ownerQq.isNotBlank()) put("owner_qq", ownerQq)
                            if (botNick.isNotBlank()) put("bot_nick", botNick)
                            if (groups.isNotBlank()) put("allowed_groups", groups)
                            if (apiKey.isNotBlank()) put("api_key", apiKey)
                        }
                        onSaveConfig(payload)
                    },
                ) { Text("保存配置", color = Color.White) }
            }
        }
    }
}

@Composable
private fun Field(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    placeholder: String,
    keyboardType: KeyboardType = KeyboardType.Text,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(bottom = 10.dp),
    ) {
        Text(label, fontSize = 11.sp, color = Color(0xFF68758B), fontWeight = FontWeight.Medium)
        Spacer(Modifier.height(5.dp))
        // BasicTextField is used instead of a styled widget so the layout stays
        // predictable across Miuix/Compose version changes.
        BasicTextField(
            value = value,
            onValueChange = onChange,
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(Color(0xFFF7F9FD))
                .padding(horizontal = 12.dp, vertical = 11.dp),
            singleLine = true,
            textStyle = TextStyle(fontSize = 12.sp, color = Color(0xFF172238)),
            keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
            cursorBrush = SolidColor(Color(0xFF3478F6)),
            decorationBox = { inner ->
                if (value.isEmpty()) {
                    Text(placeholder, fontSize = 12.sp, color = Color(0xFFB1BAC9))
                }
                inner()
            },
        )
    }
}

@Composable
private fun AboutPage() {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        CardBox {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Image(
                    painter = painterResource(R.drawable.ic_deepseek),
                    contentDescription = "DeepSeek",
                    modifier = Modifier.height(30.dp),
                )
                Text(
                    text = "  深度求索",
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF3D5AF1),
                )
            }
            Spacer(Modifier.height(10.dp))
            Text(
                text = "大肥鱼是 DeepSeek 鲸鱼娘的二创形象：蓝发、圆润、最爱吃大白饭。",
                color = Color(0xFF5B6779),
                fontSize = 12.sp,
            )
        }

        CardBox {
            Text("技术栈", fontSize = 14.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Text(
                text = "内嵌 CPython 3.12（Chaquopy）\nOneBot v11 协议\nMiuix Compose 界面\n前台服务保活",
                color = Color(0xFF5B6779),
                fontSize = 12.sp,
            )
        }

        CardBox {
            Text("版本", fontSize = 14.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Text(APP_VERSION, color = Color(0xFF79869A), fontSize = 12.sp)
        }
    }
}

@Composable
private fun CardBox(content: @Composable () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color.White, RoundedCornerShape(20.dp))
            .padding(18.dp),
    ) {
        content()
    }
}

@Composable
private fun StatusRow(label: String, value: String, good: Boolean) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 5.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, fontSize = 12.sp, color = Color(0xFF5B6779))
        Text(
            text = value,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
            color = if (good) Color(0xFF178F64) else Color(0xFF9AA4B3),
        )
    }
}