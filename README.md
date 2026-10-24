# DeepseekQbot

**应用名：** DeepseekQbot  
**Android 包名：** `com.mouya.qbotds`  
**版本：** 1.0.0  
**运行方式：** Python 机器人与本地控制面板运行在 proot；Android App 通过 `127.0.0.1:3108` 连接。

这是基于上传的“大肥鱼”QQ Bot 源码整理的应用化版本。人格卡 `bot/persona/大肥鱼.md` 与原始文件逐字节一致。Android 原工程不在上传 ZIP 中，因此没有旧 UI 可以直接复用；控制面板按你说的 iOS 风格新做，原人格与机器人流程尽量保留。

## 功能

- 在「模型」页配置 API Base、Key、模型 ID、输出 Token 与 Temperature。
- 一键读取兼容接口的 `/models`，也可手动填写模型 ID；提供聊天接口连通测试。
- 在「QQ」页检查 NapCat 登录状态、读取二维码文件、启动/停止/重启机器人。
- 管理者 QQ 和允许群列表可配置；未在允许列表中的群消息不会进入聊天记录或触发回复。
- 本地面板只绑定 `127.0.0.1`；面板令牌随机生成，API Key 不会从配置读取接口回传。
- Android 原生外壳使用 **Miuix Compose** 的 `Scaffold`、`SmallTopAppBar` 与 `NavigationBar`；面板内容由本地 WebView 展示，浏览器访问仍保留完整 Web 控制台。

## 目录

- `panel_server.py`：本地控制面板服务与 API。
- `web/index.html`：响应式 iOS 风格控制台。
- `bot/`：QQ/OneBot 逻辑、运行时设置与原人格卡。
- `android/`：Android Gradle 工程，Miuix Compose + 本地控制面板 WebView。
- `start.sh` / `stop.sh`：proot 面板启动和停止脚本。

## 一、在 proot 中启动

建议放在 proot 私有目录（例如 `~/DeepseekQbot`），不要放在 Android 共享存储目录，以降低 API Key 被其他应用读取的风险。

```bash
cd ~/DeepseekQbot
chmod +x start.sh stop.sh
./start.sh
```

启动后访问 `http://127.0.0.1:3108`。Android App 也连接此地址。面板固定只监听回环地址，不要修改成公网或局域网监听，也不要把端口转发到公网。

停止面板和本项目的机器人进程：

```bash
./stop.sh
```

所需环境：Python 3.10+。QQ 连接仍依赖你已安装并启动的 QQ + NapCat（OneBot v11）。本项目不会代替用户安装 QQ，也不会绕过 QQ 的正常扫码登录流程。

## 二、配置 API 与模型

在 App 或浏览器控制台的「模型」页填写服务商提供的配置：

- **API Base URL**：例如 `https://api.example.com/v1`，请换成服务商给出的可信地址。
- **API Key**：填写你自己的有效密钥。源码不内置真实 Key，密钥输入框留空时会保留此前已保存的 Key。
- **模型 ID**：点「获取列表」请求兼容接口 `/models`；服务商不支持模型列表时可手动输入。
- 按需设置最大输出 Token 与 Temperature，再点「测试连接」。

初始模型沿用原项目中的 `glm5.2`，不代表当前 API 服务商一定提供此模型。API Base 沿用源项目地址作为可编辑初始值；配置前请自行核对其可信度和可用性。

API Key 保存在 `bot/data/app_config.json`，程序会尽力将文件权限设为 `600`，但**不是加密存储**。不要把填好 Key 的数据目录打包或提交到 Git。

## 三、QQ / NapCat 连接与权限

「QQ」页默认配置：

- HTTP API：`http://127.0.0.1:3000`
- WebSocket：`ws://127.0.0.1:3001`

先按 NapCat 正常流程完成扫码登录，再刷新状态。面板通过 OneBot `get_login_info` 检查连接，并尝试读取 NapCat 的二维码图片文件。若默认路径不匹配，请在「权限与设置」里填写实际二维码路径，或者在启动面板前设置 `NAPCAT_QR_PATH` 环境变量。

「刷新二维码」只重新读取现有图片，不会让 NapCat 创建新二维码。二维码过期时，请按 NapCat 正常流程刷新后再读取。保存新的 NapCat 地址后，点「重启机器人」使 WebSocket 重新连接。

群消息遵循允许列表：不在列表中的群消息会被过滤，不写入聊天记录，不触发回复。管理者 QQ 默认沿用部署说明中的 `3523172449`，可以在设置页修改；仅配置的管理者私聊可把 DSH 管理指令提交到队列。把管理者 QQ 设为 `0` 可以关闭该授权路径。普通私聊仍按原机器人逻辑处理。

## 四、用 Miuix 构建 Android App

将 `android/` 作为 Android Gradle 工程导入 Android Studio 或支持 Kotlin/Compose 的 Miuix 构建环境，安装所需 Android SDK 后构建。项目使用 Miuix 的 Android Compose 工件 `miuix-ui-android` 与 `miuix-icons-android`（当前配置版本 `0.9.4`）；对应 Kotlin/Compose Gradle 插件版本为 `2.4.20`，Android Gradle Plugin 为 `8.13.2`。Miuix 仍属于实验性 UI 库，后续升级可能需要调整 API。

关键设置：

- `applicationId` / `namespace`：`com.mouya.qbotds`
- `app_name`：`DeepseekQbot`
- `minSdk`：26，`targetSdk`：35
- Java/Kotlin 目标：17
- 只声明 `INTERNET` 权限；明文 HTTP 只允许本机回环地址。
- Miuix 原生顶部栏、底部导航承载本地面板的四个主页面；没有 proot 面板时显示连接提示。

**构建说明：** 当前交付容器没有 Android SDK、Gradle 或可用的 Gradle Wrapper JAR，所以这里交付的是完整 Android 工程源码，没有声称已经生成 APK。Gradle 依赖需在构建环境联网解析。官方 Miuix 快速开始见：<https://compose-miuix-ui.github.io/miuix/zh_CN/guide/getting-started>。

启动 App 前先在 proot 执行 `./start.sh`。如显示本地服务未启动，回到 proot 启动面板后点「重新连接」。

## 五、验证与限制

- Python 源文件通过 `py_compile`；前端 JavaScript 通过 `node --check`；面板完成本地启动、配置/状态接口及未带令牌时拒绝请求的冒烟测试。
- API 模型列表与聊天测试需要你填写真实可用的 API Base 和 Key；当前没有代填或验证你的凭据。
- QQ 登录状态、二维码读取依赖设备上的 QQ/NapCat 运行状态和正确路径。
- 本交付没有包含原 ZIP 中体积很大的 Node.js 压缩包与 pip 引导器；控制面板本身只使用 Python 标准库，但原机器人若需要外部依赖，应按原项目说明安装。
