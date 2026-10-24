package com.mouya.qbotds

import android.annotation.SuppressLint
import android.graphics.Color as AndroidColor
import android.os.Bundle
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
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

private const val PANEL_URL = "http://127.0.0.1:3108/?native=1"
private val PageNames = listOf("home", "models", "qq", "settings")

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = AndroidColor.rgb(244, 246, 251)
        window.navigationBarColor = AndroidColor.WHITE
        @Suppress("DEPRECATION")
        run {
            window.decorView.systemUiVisibility =
                android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or
                    android.view.View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        }
        setContent {
            val controller = remember { ThemeController(ColorSchemeMode.Light) }
            MiuixTheme(controller = controller) {
                QbotScreen()
            }
        }
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun QbotScreen() {
    var selectedPage by remember { mutableStateOf(0) }
    var connected by remember { mutableStateOf(false) }
    var webViewRef by remember { mutableStateOf<WebView?>(null) }
    var pageLoaded by remember { mutableStateOf(false) }

    DisposableEffect(Unit) {
        onDispose {
            webViewRef?.let { view ->
                view.stopLoading()
                view.webViewClient = WebViewClient()
                view.destroy()
            }
        }
    }

    Scaffold(
        topBar = {
            SmallTopAppBar(
                title = "DeepseekQbot",
                actions = {
                    Text(
                        text = "大肥鱼",
                        modifier = Modifier.padding(end = 16.dp),
                        color = Color(0xFF3478F6),
                        fontSize = 12.sp
                    )
                }
            )
        },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = selectedPage == 0,
                    onClick = { selectPage(0) { selectedPage = 0; webViewRef } },
                    icon = MiuixIcons.Home,
                    label = "总览"
                )
                NavigationBarItem(
                    selected = selectedPage == 1,
                    onClick = { selectPage(1) { selectedPage = 1; webViewRef } },
                    icon = MiuixIcons.Link,
                    label = "模型"
                )
                NavigationBarItem(
                    selected = selectedPage == 2,
                    onClick = { selectPage(2) { selectedPage = 2; webViewRef } },
                    icon = MiuixIcons.Contacts,
                    label = "QQ"
                )
                NavigationBarItem(
                    selected = selectedPage == 3,
                    onClick = { selectPage(3) { selectedPage = 3; webViewRef } },
                    icon = MiuixIcons.Settings,
                    label = "设置"
                )
            }
        }
    ) { paddingValues: PaddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .background(Color(0xFFF4F6FB))
        ) {
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                factory = { context ->
                    WebView(context).apply {
                        webViewRef = this
                        setBackgroundColor(AndroidColor.rgb(244, 246, 251))
                        overScrollMode = WebView.OVER_SCROLL_NEVER
                        settings.apply {
                            javaScriptEnabled = true
                            domStorageEnabled = true
                            databaseEnabled = false
                            allowFileAccess = false
                            allowContentAccess = false
                            builtInZoomControls = false
                            displayZoomControls = false
                            supportZoom = false
                            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
                            javaScriptCanOpenWindowsAutomatically = false
                            setSupportMultipleWindows(false)
                        }
                        webViewClient = object : WebViewClient() {
                            override fun shouldOverrideUrlLoading(
                                view: WebView,
                                request: WebResourceRequest
                            ): Boolean {
                                val host = request.url.host
                                return host != "127.0.0.1" && host != "localhost"
                            }

                            override fun onPageFinished(view: WebView, url: String) {
                                super.onPageFinished(view, url)
                                pageLoaded = true
                                connected = url.startsWith("http://127.0.0.1:3108")
                                view.evaluateJavascript("showPage('${PageNames[selectedPage]}')", null)
                            }

                            override fun onReceivedError(
                                view: WebView,
                                request: WebResourceRequest,
                                error: WebResourceError
                            ) {
                                super.onReceivedError(view, request, error)
                                if (request.isForMainFrame) {
                                    connected = false
                                    pageLoaded = false
                                }
                            }
                        }
                        loadUrl(PANEL_URL)
                    }
                },
                update = { view ->
                    if (connected && pageLoaded) {
                        view.evaluateJavascript("if(typeof showPage==='function'){showPage('${PageNames[selectedPage]}')}", null)
                    }
                }
            )
            if (!connected) {
                StartupOverlay(
                    onRetry = {
                        connected = false
                        pageLoaded = false
                        webViewRef?.loadUrl(PANEL_URL)
                    }
                )
            }
        }
    }
}

private inline fun selectPage(index: Int, update: () -> WebView?) {
    val view = update()
    view?.evaluateJavascript("if(typeof showPage==='function'){showPage('${PageNames[index]}')}", null)
}

@Composable
private fun StartupOverlay(onRetry: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFFF4F6FB))
            .padding(horizontal = 28.dp, vertical = 26.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Color.White, RoundedCornerShape(28.dp))
                .padding(24.dp),
            contentAlignment = Alignment.Center
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(text = "🐟", fontSize = 38.sp)
                Spacer(Modifier.height(14.dp))
                Text(text = "本鲸在此。", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "先在 proot 中启动本地面板",
                    color = Color(0xFF79869A),
                    fontSize = 13.sp
                )
                Spacer(Modifier.height(20.dp))
                Button(onClick = onRetry, modifier = Modifier.fillMaxWidth()) {
                    Text("重新连接", color = Color.White)
                }
                Spacer(Modifier.height(12.dp))
                Text(
                    text = "cd ~/DeepseekQbot && ./start.sh",
                    color = Color(0xFF7D8799),
                    fontSize = 11.sp
                )
            }
        }
    }
}
