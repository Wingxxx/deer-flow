# DeerFlowApp — uni-app Shell

A minimal [uni-app](https://uniapp.dcloud.net.cn/) (Vue 3) shell that wraps a [DeerFlow](https://github.com/Wingxxx/deer-flow) server in a full-screen WebView and packages it as an iOS/Android app via HBuilderX cloud build.

## Project Structure

```
DeerFlowApp/
├── DeerFlowApp/
│   ├── config.js         # Server URL default
│   ├── pages/index/      # WebView + Error Overlay + URL Config Panel
│   ├── App.vue           # App lifecycle hooks
│   ├── main.js           # Vue 3 app entry
│   ├── pages.json        # Route configuration
│   ├── manifest.json     # App config & cloud build settings
│   └── ...
├── docs/                 # Design docs & bug fix history
└── README.md
```

## Development

### Prerequisites
- [HBuilderX](https://www.dcloud.io/hbuilderx.html) (App development edition)
- Android device with USB debugging enabled (for Android build)
- Apple Developer account (for iOS build, $99/year)

### Run on Device
1. Open `DeerFlowApp/DeerFlowApp` in HBuilderX
2. Connect phone via USB
3. `Run → Run to Phone or Simulator → Android/iOS`

### Build for Distribution
- **Android**: `Publish → Native App Cloud Build → Android (.apk)`
- **iOS**: `Publish → Native App Cloud Build → iOS (.ipa)`

## Configuration

### Default Server URL
Edit [config.js](DeerFlowApp/DeerFlowApp/config.js) before cloud build:
```js
export default {
  serverUrl: 'http://192.168.1.56:2026/'
}
```

### Runtime URL Change
Tap the **⚙ FAB** (bottom-right) in the app to change the server URL at runtime. The app validates the URL via `GET /health` before saving.

## Notes
- Server URL is configured via `config.js` — edit before cloud build
- DeerFlow frontend updates are reflected automatically (no rebuild needed)
- No native plugins, no third-party SDKs, no business logic
