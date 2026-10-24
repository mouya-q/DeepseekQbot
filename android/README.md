# DeepseekQbot Android

- App label: `DeepseekQbot`
- Package: `com.mouya.qbotds`
- UI: Miuix Compose (`Scaffold`, `SmallTopAppBar`, `NavigationBar`) + WebView for the local controller.
- Dependencies: Miuix `0.9.4`, Kotlin / Compose Gradle plugin `2.4.20`, Android Gradle Plugin `8.13.2`.
- Android SDK: compile 35, min 26, target 35; only `INTERNET` permission.

Open this directory as an Android Gradle project after installing the matching Android SDK and Gradle environment. Build with `gradle assembleDebug` (or use your IDE's Build APK action). Maven dependencies must be downloaded in the build environment.

Before opening the app, start the Python control panel from the proot project root with `./start.sh`. The app connects to `http://127.0.0.1:3108`; this port is restricted to the local loopback interface.

The project source has been prepared but no APK is included: the creation environment did not have Android SDK or Gradle installed.
