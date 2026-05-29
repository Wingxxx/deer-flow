<template>
  <view>
    <web-view v-if="showWebView" :src="webviewSrc" @title="onTitle" @load="onWebViewLoad" @error="onWebViewError"></web-view>

    <view v-if="showErrorOverlay" class="error-overlay">
      <view class="error-content">
        <view class="error-icon">⚠️</view>
        <view class="error-title">无法连接服务器</view>
        <view class="error-desc">当前网络无法访问指定的服务器地址。请检查网络连接或修改服务器地址。</view>
        <view class="url-card">
          <view class="url-label">当前地址</view>
          <view class="url-value">{{ currentUrl }}</view>
        </view>
        <view class="error-actions">
          <view class="btn btn-scan" @click="scanQRCode">📷 扫码自动绑定</view>
          <view class="btn btn-primary" @click="openConfigPanel">✏️ 修改服务器地址</view>
          <view class="btn btn-secondary" @click="retryLoad">🔄 检查网络并重试</view>
        </view>
      </view>
    </view>

    <view v-if="showConfigPanel" class="config-overlay">
      <view class="config-mask" @click="closeConfigPanel"></view>
      <view class="config-panel">
        <view class="config-header">
          <view class="config-title">服务器设置</view>
          <view class="config-close" @click="closeConfigPanel">✕</view>
        </view>

        <view class="form-group">
          <view class="form-label">服务器地址</view>
          <input class="form-input" type="text" :value="inputUrl" @input="onUrlInput" @blur="autoCompleteProtocol" placeholder="请输入服务器地址" />
          <view v-if="urlHint" class="form-hint" :class="{ 'hint-warn': urlHintType === 'warn', 'hint-error': urlHintType === 'error' }">{{ urlHint }}</view>
        </view>

        <view class="form-group">
          <view class="btn btn-outline" @click="testConnection">🔌 测试连接</view>
        </view>

        <view class="form-group">
          <view class="btn btn-scan" @click="scanQRCode">📷 扫码自动绑定</view>
        </view>

        <view v-if="testResult.message" class="test-result" :class="'result-' + testResult.type">
          <view>{{ testResult.message }}</view>
        </view>

        <view class="config-actions">
          <view class="btn btn-primary" :class="{ 'btn-disabled': saveDisabled }" @click="saveAndLoad">💾 保存并加载</view>
          <view class="btn btn-secondary" @click="restoreDefaultUrl">↩️ 恢复默认地址</view>
        </view>
      </view>
    </view>

    <view v-if="!showConfigPanel" class="settings-trigger" @click="openConfigPanel">⚙</view>
  </view>
</template>

<script>
import appConfig from '../../config.js'

var PUBLIC_DOMAINS = [
  'baidu.com', 'google.com', 'googleapis.com', 'github.com', 'microsoft.com',
  'apple.com', 'qq.com', 'taobao.com', 'tmall.com', 'jd.com', '163.com',
  'sina.com', 'weibo.com', 'sohu.com', 'yahoo.com', 'facebook.com',
  'twitter.com', 'instagram.com', 'youtube.com', 'reddit.com', 'amazon.com',
  'bing.com', 'aliyun.com', 'tencent.com', 'bytedance.com', 'xiaomi.com'
]

function isPublicDomain(url) {
  try {
    var hostname = url.replace(/^https?:\/\//, '').split('/')[0].split(':')[0]
    if (/^(\d{1,3}\.){3}\d{1,3}$/.test(hostname)) {
      var parts = hostname.split('.').map(Number)
      if (parts[0] === 10) return false
      if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return false
      if (parts[0] === 192 && parts[1] === 168) return false
      if (parts[0] === 127) return false
      return false
    }
    for (var i = 0; i < PUBLIC_DOMAINS.length; i++) {
      if (hostname === PUBLIC_DOMAINS[i] || hostname.endsWith('.' + PUBLIC_DOMAINS[i])) {
        return true
      }
    }
    return false
  } catch (e) {
    return false
  }
}

function isValidUrl(str) {
  if (!str || str.length === 0) return false
  if (str.indexOf(' ') !== -1) return false
  if (/^https?:\/\//.test(str)) return true
  return true
}

function autoProtocol(url) {
  if (!url) return url
  if (/^https?:\/\//i.test(url)) return url
  if (url.indexOf('://') !== -1) return url
  return 'http://' + url
}

export default {
  data() {
    return {
      webviewSrc: '',
      showWebView: true,
      showErrorOverlay: false,
      showConfigPanel: false,
      currentUrl: '',
      inputUrl: '',
      urlHint: '',
      urlHintType: '',
      testResult: { type: '', message: '' },
      saveDisabled: true,
      retryCount: 0,
      retryTimer: null,
      scanning: false
    }
  },
  onShow() {
    var configUrl = appConfig.serverUrl
    var customUrl = uni.getStorageSync('df_custom_url')
    var targetUrl = customUrl || configUrl

    if (targetUrl !== this.webviewSrc) {
      this.webviewSrc = targetUrl
      this.currentUrl = targetUrl
      this.showWebView = true
      this.showErrorOverlay = false
    }

    if (!this._networkListenerRegistered) {
      this._networkListenerRegistered = true
      uni.onNetworkStatusChange(function(res) {
        if (res.isConnected && this.showErrorOverlay) {
          plus.nativeUI.toast('网络已恢复，点击重试加载')
        }
      }.bind(this))
    }

    // 清理旧的 df_server_url（v2 升级遗留兼容）
    if (uni.getStorageSync('df_server_url')) {
      uni.removeStorageSync('df_server_url')
    }
  },
  onReady() {
    setTimeout(this.injectFix, 1000)
  },
  methods: {
    onTitle(e) {
      uni.setNavigationBarTitle({ title: e.title })
    },
    onWebViewLoad(e) {
      this.showErrorOverlay = false
      this.showWebView = true
      this.retryCount = 0
      if (this.retryTimer) {
        clearTimeout(this.retryTimer)
        this.retryTimer = null
      }
    },
    onWebViewError(e) {
      this.showWebView = false
      this.showErrorOverlay = true
      this.currentUrl = this.webviewSrc
    },

    openConfigPanel() {
      this.inputUrl = this.webviewSrc
      this.urlHint = ''
      this.urlHintType = ''
      this.testResult = { type: '', message: '' }
      this.saveDisabled = true
      this.showConfigPanel = true
    },
    closeConfigPanel() {
      this.showConfigPanel = false
    },

    scanQRCode() {
      var self = this
      if (self.scanning) return
      self.scanning = true

      uni.scanCode({
        scanType: ['qrCode'],
        success: function(res) {
          self.scanning = false
          var result = res.result
          if (!result || result.length === 0) {
            plus.nativeUI.toast('二维码内容无效，请扫描 DeerFlow 服务器地址')
            return
          }
          self.processScannedUrl(result)
        },
        fail: function(err) {
          self.scanning = false
          var msg = err.errMsg || ''
          if (msg.indexOf('cancel') !== -1) {
            return
          }
          if (msg.indexOf('permission') !== -1) {
            plus.nativeUI.toast('需要相机权限才能扫码，请在系统设置中开启')
          } else {
            plus.nativeUI.toast('扫码失败: ' + msg)
          }
        }
      })
    },

    processScannedUrl(url) {
      if (url.indexOf(' ') !== -1 || /[\u4e00-\u9fa5]/.test(url)) {
        plus.nativeUI.toast('二维码内容无效，请扫描 DeerFlow 服务器地址')
        return
      }

      if (!/^https?:\/\//i.test(url)) {
        if (url.indexOf('://') !== -1) {
          plus.nativeUI.toast('不支持的协议类型，请扫描 HTTP 服务器地址')
          return
        }
        url = 'http://' + url
      }

      var publicDomain = isPublicDomain(url)

      if (publicDomain) {
        plus.nativeUI.toast('您扫描的是一个公共网站地址，DeerFlow 服务器通常位于内网')
      }

      var self = this
      self.testResult = { type: 'loading', message: '正在验证服务器身份...' }

      uni.request({
        url: url + '/health',
        method: 'GET',
        timeout: 5000,
        success: function(res) {
          if (res.data && res.data.service === 'deer-flow-gateway' && res.data.status === 'healthy') {
            self.inputUrl = url
            self.autoCompleteProtocol()

            if (url !== appConfig.serverUrl) {
              uni.setStorageSync('df_custom_url', url)
            } else {
              uni.removeStorageSync('df_custom_url')
            }

            self.webviewSrc = url
            self.currentUrl = url
            self.showConfigPanel = false
            self.showErrorOverlay = false
            self.showWebView = true
            self.retryCount = 0
            if (self.retryTimer) {
              clearTimeout(self.retryTimer)
              self.retryTimer = null
            }

            plus.nativeUI.toast('扫码绑定成功: ' + url)
          } else {
            if (self.showConfigPanel === false) {
              self.openConfigPanel()
              self.inputUrl = url
            }
            self.testResult = { type: 'fail', message: '⛔ 该服务器不是 DeerFlow 网关，禁止使用' }
          }
        },
        fail: function(err) {
          var msg = err.errMsg || ''
          if (self.showConfigPanel === false) {
            self.openConfigPanel()
            self.inputUrl = url
          }
          if (msg.indexOf('timeout') !== -1) {
            self.testResult = { type: 'fail', message: '❌ 连接超时（5秒），请检查地址或网络' }
          } else {
            self.testResult = { type: 'fail', message: '❌ 无法连接，请检查地址或网络' }
          }
        }
      })
    },

    onUrlInput(e) {
      var val = e.detail.value
      this.inputUrl = val

      if (!val || val.length === 0) {
        this.urlHint = '请输入服务器地址'
        this.urlHintType = 'error'
        this.saveDisabled = true
        this.testResult = { type: '', message: '' }
        return
      }

      if (val.indexOf(' ') !== -1) {
        this.urlHint = '地址格式不正确（不能包含空格）'
        this.urlHintType = 'error'
        this.saveDisabled = true
        this.testResult = { type: '', message: '' }
        return
      }

      if (/[\u4e00-\u9fa5]/.test(val)) {
        this.urlHint = '地址格式不正确（不能包含中文）'
        this.urlHintType = 'error'
        this.saveDisabled = true
        this.testResult = { type: '', message: '' }
        return
      }

      var withProtocol = autoProtocol(val)
      if (isPublicDomain(withProtocol)) {
        this.urlHint = '您输入的似乎是一个公共网站地址。DeerFlow 服务器通常位于内网（如 192.168.x.x）'
        this.urlHintType = 'warn'
      } else {
        this.urlHint = ''
        this.urlHintType = ''
      }

      this.saveDisabled = true
      this.testResult = { type: '', message: '' }
    },

    autoCompleteProtocol() {
      if (this.inputUrl && !/^https?:\/\//i.test(this.inputUrl) && this.inputUrl.indexOf('://') === -1) {
        this.inputUrl = 'http://' + this.inputUrl
      }
    },

    testConnection() {
      this.autoCompleteProtocol()
      var url = this.inputUrl
      if (!url || !/^https?:\/\//.test(url)) {
        this.testResult = { type: 'fail', message: '❌ 请输入有效的服务器地址' }
        return
      }

      this.testResult = { type: 'loading', message: '正在测试连接...' }

      var self = this
      uni.request({
        url: url + '/health',
        method: 'GET',
        timeout: 5000,
        success: function(res) {
          if (res.data && res.data.service === 'deer-flow-gateway' && res.data.status === 'healthy') {
            self.testResult = { type: 'success', message: '✅ DeerFlow 服务器已验证 ✓' }
            self.saveDisabled = false
          } else {
            self.testResult = { type: 'fail', message: '⛔ 非 DeerFlow 服务器，禁止使用' }
            self.saveDisabled = true
          }
        },
        fail: function(err) {
          var msg = err.errMsg || ''
          if (msg.indexOf('timeout') !== -1) {
            self.testResult = { type: 'fail', message: '❌ 连接超时（5秒），请检查地址或网络' }
          } else {
            self.testResult = { type: 'fail', message: '❌ 无法连接，请检查地址或网络' }
          }
          self.saveDisabled = true
        }
      })
    },

    saveAndLoad() {
      if (this.saveDisabled) return

      var url = this.inputUrl
      this.autoCompleteProtocol()
      url = this.inputUrl

      // 只保存自定义 URL（与 config.js 默认不同的才存）
      if (url !== appConfig.serverUrl) {
        uni.setStorageSync('df_custom_url', url)
      } else {
        uni.removeStorageSync('df_custom_url')
      }

      this.webviewSrc = url
      this.currentUrl = url
      this.showConfigPanel = false
      this.showErrorOverlay = false
      this.showWebView = true
      this.retryCount = 0

      if (this.retryTimer) {
        clearTimeout(this.retryTimer)
        this.retryTimer = null
      }

      plus.nativeUI.toast('已保存并加载: ' + url)
    },

    restoreDefaultUrl() {
      uni.removeStorageSync('df_custom_url')
      this.inputUrl = appConfig.serverUrl
      this.urlHint = ''
      this.urlHintType = ''
      this.testResult = { type: '', message: '' }
      this.saveDisabled = true
    },

    retryLoad() {
      this.showErrorOverlay = false
      this.showWebView = true

      var src = this.webviewSrc
      this.webviewSrc = ''
      var self = this
      setTimeout(function() {
        self.webviewSrc = src
      }, 50)

      this.scheduleRetry()
    },

    scheduleRetry() {
      var delays = [2000, 4000, 8000, 15000]
      var index = this.retryCount
      if (index >= delays.length) return
      if (this.retryTimer) clearTimeout(this.retryTimer)
      this.retryTimer = setTimeout(function() {
        this.retryCount++
        this.retryLoad()
      }.bind(this), delays[index])
    },

    injectFix(attempt) {
      attempt = attempt || 0
      if (attempt > 5) return
      if (!this.showWebView) {
        setTimeout(function() { this.injectFix(attempt + 1) }.bind(this), 1000)
        return
      }

      try {
        var pw = this.$scope.$getAppWebview()
        if (!pw) { try { pw = plus.webview.currentWebview() } catch (e) {} }
        if (!pw) { setTimeout(function() { this.injectFix(attempt + 1) }.bind(this), 1000); return }

        var wv = (pw.children() && pw.children().length > 0) ? pw.children()[0] : pw

        var injectedFn = function() {
          var D = document
          if (D.__ok) return
          D.__ok = true

          var origPD = Event.prototype.preventDefault
          Event.prototype.preventDefault = function() {
            var t = this.target
            if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.tagName === 'BUTTON' || t.tagName === 'A')) return
            if (t && t.closest) {
              if (t.closest('input,textarea,select,button,a,[contenteditable]')) return
            }
            return origPD.apply(this, arguments)
          }

          var cs = D.createElement('style')
          cs.textContent = '*{pointer-events:auto!important}input,textarea,select,button,a{-webkit-user-select:text!important;user-select:text!important;touch-action:manipulation!important}'
          cs.id = '__xs'

          function apply() {
            if (!D.body) return
            if (!D.getElementById('__xs')) (D.head || D.body).appendChild(cs.cloneNode(true))
            var es = D.querySelectorAll('input,textarea,select,button,a')
            for (var i = 0; i < es.length; i++) {
              es[i].style.pointerEvents = 'auto'
              es[i].style.webkitUserSelect = 'text'
              es[i].style.userSelect = 'text'
              es[i].style.touchAction = 'manipulation'
              if (es[i].disabled) es[i].disabled = false
              if (es[i].readOnly) es[i].readOnly = false
            }
          }

          D.addEventListener('mousedown', function(e) {
            var t = e.target
            if (!t) return
            if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT') {
              t.focus()
              try { t.click() } catch (e) {}
            } else if (t.tagName === 'BUTTON' || t.tagName === 'A') {
              try { t.click() } catch (e) {}
            }
          }, { capture: true, passive: false })

          D.addEventListener('touchstart', function(e) {
            var t = e.target
            if (!t) return
            if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT') {
              t.focus()
              try { t.click() } catch (e) {}
            } else if (t.tagName === 'BUTTON' || t.tagName === 'A') {
              try { t.click() } catch (e) {}
            }
          }, { capture: true, passive: false })

          apply()

          var mo = new MutationObserver(function() { apply() })
          if (D.body) mo.observe(D.body, { childList: true, subtree: true })

          var ps = history.pushState, rs = history.replaceState
          history.pushState = function() { var r = ps.apply(this, arguments); setTimeout(apply, 300); return r }
          history.replaceState = function() { var r = rs.apply(this, arguments); setTimeout(apply, 300); return r }
          D.addEventListener('popstate', function() { setTimeout(apply, 300) })
        }

        wv.evalJS('(' + injectedFn.toString() + ')()')
      } catch (e) {
        setTimeout(function() { this.injectFix(attempt + 1) }.bind(this), 1000)
      }
    }
  }
}
</script>

<style>
.error-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9998;
}
.error-content {
  width: 85%;
  max-width: 340px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.error-icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: #fef0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 40px;
  margin-bottom: 20px;
  color: #ee0a24;
}
.error-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #1d1d1f;
}
.error-desc {
  font-size: 14px;
  color: #86868b;
  text-align: center;
  line-height: 1.6;
  margin-bottom: 20px;
}
.url-card {
  width: 100%;
  background: #f5f5f7;
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 16px;
}
.url-label {
  font-size: 11px;
  color: #86868b;
  margin-bottom: 4px;
}
.url-value {
  font-size: 14px;
  color: #1d1d1f;
  word-break: break-all;
}
.error-actions {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.config-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9998;
}
.config-mask {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.4);
}
.config-panel {
  width: 85%;
  max-width: 340px;
  background: #ffffff;
  border-radius: 16px;
  padding: 20px;
  position: relative;
  box-shadow: 0 4px 24px rgba(0,0,0,0.15);
}
.config-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.config-title {
  font-size: 18px;
  font-weight: 600;
  color: #1d1d1f;
}
.config-close {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #f5f5f7;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: #86868b;
}

.form-group {
  margin-bottom: 14px;
}
.form-label {
  font-size: 13px;
  font-weight: 500;
  color: #555;
  margin-bottom: 6px;
}
.form-input {
  width: 100%;
  padding: 12px 14px;
  border: 1.5px solid #e5e5ea;
  border-radius: 10px;
  font-size: 15px;
  outline: none;
  box-sizing: border-box;
  background: #fff;
  color: #1d1d1f;
}
.form-input:focus {
  border-color: #007aff;
}
.form-hint {
  font-size: 12px;
  margin-top: 4px;
  color: #86868b;
}
.hint-warn {
  color: #f5a623;
}
.hint-error {
  color: #ee0a24;
}

.test-result {
  margin-top: 6px;
  margin-bottom: 14px;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.5;
}
.result-success {
  background: #f0f9eb;
  color: #07c160;
  border: 1px solid #c8e6c9;
}
.result-fail {
  background: #fef0f0;
  color: #ee0a24;
  border: 1px solid #ffcdd2;
}
.result-loading {
  background: #f5f5f7;
  color: #86868b;
  border: 1px solid #e0e0e0;
}

.config-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 4px;
}

.btn {
  text-align: center;
  padding: 14px;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 500;
}
.btn-primary {
  background: #007aff;
  color: #fff;
}
.btn-disabled {
  background: #ccc;
  color: #999;
}
.btn-secondary {
  background: #f5f5f7;
  color: #007aff;
}
.btn-outline {
  background: transparent;
  color: #007aff;
  border: 1.5px solid #007aff;
  box-sizing: border-box;
}

.settings-trigger {
  position: fixed;
  right: 10px;
  bottom: 100px;
  width: 44px;
  height: 44px;
  line-height: 44px;
  text-align: center;
  font-size: 24px;
  background: rgba(0,0,0,0.5);
  color: #fff;
  border-radius: 50%;
  z-index: 9999;
}

.btn-scan {
  text-align: center;
  padding: 14px;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 500;
  background: #e8f5e9;
  color: #2e7d32;
  border: 1.5px solid #a5d6a7;
  box-sizing: border-box;
}
</style>
