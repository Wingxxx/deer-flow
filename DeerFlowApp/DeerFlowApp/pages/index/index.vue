<template>
  <view>
    <view v-if="isLoading" class="loading-splash">
      <image class="loading-brand" src="/static/brand.png" mode="aspectFit"></image>
      <view class="loading-spinner"></view>
      <view class="loading-text">正在连接 DeerFlow 服务器...</view>
    </view>

    <view :class="['webview-container', { 'webview-hidden': !showWebView }]">
      <web-view v-show="showWebView" :src="webviewSrc" @load="onWebViewLoad" @error="onWebViewError"></web-view>
    </view>

    <view v-show="showErrorOverlay" class="error-overlay">
      <view class="error-content">
        <view class="error-icon">⚠️</view>
        <view class="error-title">无法连接服务器</view>
        <view class="error-desc">当前网络无法访问指定的服务器地址。请检查网络连接或修改服务器地址。</view>
        <view v-if="webViewError" class="error-detail">{{ webViewError }}</view>
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

    <view v-if="showConfigPanel" class="config-overlay" :key="'config-' + configKey">
      <view class="config-mask" @click="closeConfigPanel"></view>
      <view class="config-panel">
        <view class="config-header">
          <view class="config-title">服务器设置</view>
          <view class="config-close" @click="closeConfigPanel">✕</view>
        </view>

        <view class="form-group">
          <view class="form-label">当前服务器地址</view>
          <view class="url-card">
            <view class="url-value">{{ inputUrl || '（未设置）' }}</view>
          </view>
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

        <view v-if="testResult.type === 'fail'" class="log-actions">
          <view class="btn btn-log" @click="viewScanLog">📋 查看日志</view>
          <view class="btn btn-log-clear" @click="clearScanLog">🗑 清空日志</view>
        </view>
      </view>
    </view>

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
      isLoading: true,
      showWebView: true,
      showErrorOverlay: false,
      showConfigPanel: false,
      currentUrl: '',
      inputUrl: '',
      testResult: { type: '', message: '' },
      retryCount: 0,
      retryTimer: null,
      scanning: false,
      webViewError: '',
      configKey: 0
    }
  },
  onShow() {
    var configUrl = appConfig.serverUrl

    if (configUrl !== this.webviewSrc) {
      this.webviewSrc = configUrl
      this.currentUrl = configUrl
      this.showWebView = false
      this.showErrorOverlay = false
      this.isLoading = true
    }

    this.createFloatBtn()
    if (this.showConfigPanel) {
      this.destroyFloatBtn()
    }

    if (!this._networkListenerRegistered) {
      this._networkListenerRegistered = true
      uni.onNetworkStatusChange(function(res) {
        if (res.isConnected && this.showErrorOverlay) {
          plus.nativeUI.toast('网络已恢复，点击重试加载')
        }
      }.bind(this))
    }

    this.checkServerConnection(configUrl)
  },
  onReady() {
    this.createFloatBtn()
    setTimeout(this.injectFix, 1000)
  },
  onHide() {
    this.destroyFloatBtn()
  },
  methods: {
    checkServerConnection(url) {
      var self = this
      var healthUrl = url.replace(/\/+$/, '') + '/health'

      uni.getNetworkType({
        success: function(netRes) {
          var noNetwork = (netRes.networkType === 'none')
          if (noNetwork) {
            self.isLoading = false
            self.showErrorOverlay = true
            self.showWebView = false
            self.webViewError = '📶 设备未连接网络，请检查 Wi-Fi 或移动数据'
            self.currentUrl = url
            return
          }

          uni.request({
            url: healthUrl,
            method: 'GET',
            timeout: 5000,
            success: function(res) {
              self.isLoading = false
              var isValid = false
              if (res.data && res.data.service === 'deer-flow-gateway' && res.data.status === 'healthy') isValid = true
              if (res.data && res.data.detail && res.data.detail.code === 'not_authenticated') isValid = true
              if (res.statusCode === 401 || res.statusCode === 403) isValid = true

              if (isValid) {
                self.showWebView = true
                self.showErrorOverlay = false
                self.webViewError = ''
              } else {
                self.showWebView = false
                self.showErrorOverlay = true
                self.webViewError = '🔌 无法连接服务器（服务器地址错误或 DeerFlow 服务未启动）'
                self.currentUrl = url
              }
            },
            fail: function(err) {
              self.isLoading = false
              self.showWebView = false
              self.showErrorOverlay = true
              var msg = err.errMsg || ''
              if (msg.indexOf('timeout') !== -1) {
                self.webViewError = '🔌 连接超时（5秒），请检查服务器地址或网络'
              } else {
                self.webViewError = '🔌 无法连接服务器（' + msg + '）'
              }
              self.currentUrl = url
            }
          })
        },
        fail: function() {
          self.isLoading = false
          self.showWebView = true
        }
      })
    },

    createFloatBtn() {
      if (typeof plus === 'undefined' || !plus.nativeObj) return
      try {
        this.destroyFloatBtn()
        var self = this

        function circleImg(size, opacity) {
          var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + size + '" height="' + size + '">' +
            '<circle cx="' + (size / 2) + '" cy="' + (size / 2) + '" r="' + (size / 2) + '" ' +
            'fill="rgba(255,255,255,' + opacity + ')"/>' +
            '</svg>'
          return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
        }

        var btn = new plus.nativeObj.View('settings-float-btn', {
          top: '80%',
          left: '85%',
          width: '44px',
          height: '44px'
        }, [
          {
            tag: 'img',
            src: circleImg(44, 0.7),
            position: { top: 0, left: 0, width: '44', height: '44' }
          },
          {
            tag: 'font',
            text: '⚙',
            textStyles: {
              size: '20px',
              color: '#555555',
              alignment: 'center',
              verticalAlign: 'middle'
            },
            position: { top: 0, left: 0, width: '44', height: '44' }
          }
        ])
        btn.addEventListener('click', function() {
          self.openConfigPanel()
        })
        btn.show()
        this._floatBtn = btn
      } catch (e) {
        this.writeLog('[Native] 创建悬浮按钮失败: ' + JSON.stringify(e))
      }
    },

    destroyFloatBtn() {
      try {
        if (this._floatBtn) {
          this._floatBtn.close()
          this._floatBtn = null
        }
      } catch (e) {}
    },

    onWebViewLoad(e) {
      this.showErrorOverlay = false
      this.showWebView = true
      this.webViewError = ''
      this.retryCount = 0
      if (this.retryTimer) {
        clearTimeout(this.retryTimer)
        this.retryTimer = null
      }
    },
    onWebViewError(e) {
      var err = e.detail || e
      var errStr = JSON.stringify(err)
      this.webViewError = errStr
      this.showWebView = false
      this.showErrorOverlay = true
      this.currentUrl = this.webviewSrc
      var log = '[WebView] 加载错误, URL: ' + this.webviewSrc + ', 详情: ' + errStr
      this.writeLog(log)
    },

    openConfigPanel() {
      this.destroyFloatBtn()
      this.showErrorOverlay = false
      this.testResult = { type: '', message: '' }
      this.inputUrl = this.webviewSrc
      this.showWebView = false
      this.configKey++
      this.showConfigPanel = true
    },
    closeConfigPanel() {
      this.showConfigPanel = false
      this.showWebView = true
      this.createFloatBtn()
    },

    writeLog(msg) {
      try {
        plus.io.requestFileSystem(plus.io.PRIVATE_DOC, function(fs) {
          fs.root.getFile('df_scan_log.txt', { create: true }, function(entry) {
            entry.createWriter(function(writer) {
              writer.seek(writer.length)
              var time = new Date().toLocaleString()
              writer.write(time + ' ' + msg + '\n')
            })
          })
        })
      } catch (e) {}
    },

    viewScanLog() {
      var self = this
      try {
        plus.io.requestFileSystem(plus.io.PRIVATE_DOC, function(fs) {
          fs.root.getFile('df_scan_log.txt', { create: false }, function(entry) {
            entry.file(function(file) {
              var reader = new plus.io.FileReader()
              reader.onloadend = function(e) {
                var content = e.target.result || '(空)'
                var msgs = content.split('\n').filter(function(l) { return l.trim().length > 0 })
                var summary = msgs.join('\n')
                plus.nativeUI.alert('扫码日志 (' + msgs.length + '条):\n\n' + (summary || '(无记录)'), '扫码日志')
              }
              reader.readAsText(file)
            }, function() {
              plus.nativeUI.alert('暂无日志记录', '扫码日志')
            })
          }, function() {
            plus.nativeUI.alert('暂无日志记录', '扫码日志')
          })
        })
      } catch (e) {
        plus.nativeUI.alert('读取日志失败: ' + JSON.stringify(e), '扫码日志')
      }
    },

    clearScanLog() {
      var self = this
      try {
        plus.io.requestFileSystem(plus.io.PRIVATE_DOC, function(fs) {
          fs.root.getFile('df_scan_log.txt', { create: false }, function(entry) {
            entry.createWriter(function(writer) {
              writer.truncate(0)
              writer.onwriteend = function() {
                plus.nativeUI.toast('日志已清空')
              }
            })
          })
        })
      } catch (e) {
        plus.nativeUI.toast('清空失败')
      }
    },

    scanQRCode() {
      var self = this
      if (self.scanning) {
        plus.nativeUI.toast('扫码正在进行中...')
        return
      }
      self.scanning = true

      var scanTimer = setTimeout(function() {
        self.scanning = false
        self.writeLog('[扫码] 超时释放 scanning')
      }, 10000)

      function releaseScan() {
        clearTimeout(scanTimer)
        self.scanning = false
      }

      var deviceInfo = ''
      try {
        deviceInfo = plus.device.model || plus.os.name || ''
      } catch (e) {}
      self.writeLog('[扫码] 开始, 设备: ' + deviceInfo + ', 平台: ' + (plus.os ? plus.os.name : ''))

      try {
        uni.scanCode({
          scanType: ['qrCode'],
          success: function(res) {
            releaseScan()
            self.writeLog('[扫码] 成功, 结果: ' + (res.result || ''))
            var result = res.result
            if (!result || result.length === 0) {
              plus.nativeUI.toast('二维码内容无效，请扫描 DeerFlow 服务器地址')
              return
            }
            self.processScannedUrl(result)
          },
          fail: function(err) {
            releaseScan()
            var msg = err.errMsg || ''
            var detail = JSON.stringify(err)
            self.writeLog('[扫码] 失败, message: ' + msg + ', 完整: ' + detail)

            if (msg.indexOf('cancel') !== -1) {
              return
            }

            var failMsg = ''
            if (msg.indexOf('permission') !== -1) {
              failMsg = '需要相机权限才能扫码，请在系统设置中开启'
            } else {
              failMsg = '扫码失败: ' + msg
            }

            plus.nativeUI.toast(failMsg)

            if (self.showConfigPanel) {
              self.testResult = { type: 'fail', message: failMsg + '\n\n完整错误:\n' + detail + '\n\n日志已保存至: df_scan_log.txt' }
            } else {
              self.openConfigPanel()
              self.inputUrl = self.webviewSrc
              self.testResult = { type: 'fail', message: failMsg + '\n\n完整错误:\n' + detail + '\n\n日志已保存至: df_scan_log.txt' }
            }
          }
        })
      } catch (e) {
        releaseScan()
        var detail = JSON.stringify(e)
        self.writeLog('[扫码] scan 调用异常: ' + detail)
        plus.nativeUI.toast('扫码异常: ' + (e.message || ''))
        if (self.showConfigPanel) {
          self.testResult = { type: 'fail', message: '扫码调用异常\n\n' + detail }
        } else {
          self.openConfigPanel()
          self.inputUrl = self.webviewSrc
          self.testResult = { type: 'fail', message: '扫码调用异常\n\n' + detail }
        }
      }
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
        url: url.replace(/\/+$/, '') + '/health',
        method: 'GET',
        timeout: 5000,
        success: function(res) {
          var responseStr = JSON.stringify(res.data)
          var statusCode = res.statusCode || 0
          self.writeLog('[health] 响应状态码: ' + statusCode + ', 数据: ' + responseStr)

          var isValid = false

          if (res.data && res.data.service === 'deer-flow-gateway' && res.data.status === 'healthy') {
            isValid = true
          }

          if (res.data && res.data.detail && res.data.detail.code === 'not_authenticated') {
            isValid = true
          }

          if (statusCode === 401 || statusCode === 403) {
            isValid = true
          }

          if (isValid) {
            self.inputUrl = url
            self.autoCompleteProtocol()

            self.webviewSrc = url
            self.currentUrl = url
            self.showConfigPanel = false
            self.showErrorOverlay = false
            self.showWebView = true
            self.webViewError = ''
            self.createFloatBtn()
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
            var msg = '⛔ 非 DeerFlow 服务器，禁止使用\n返回: ' + responseStr
            self.testResult = { type: 'fail', message: msg }
            self.writeLog('[health] 身份验证失败: ' + responseStr)
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
        url: url.replace(/\/+$/, '') + '/health',
        method: 'GET',
        timeout: 5000,
        success: function(res) {
          var data = res.data
          var statusCode = res.statusCode || 0
          var isValid = false

          if (data && data.service === 'deer-flow-gateway' && data.status === 'healthy') {
            isValid = true
          }

          if (data && data.detail && data.detail.code === 'not_authenticated') {
            isValid = true
          }

          if (statusCode === 401 || statusCode === 403) {
            isValid = true
          }

          if (isValid) {
            self.testResult = { type: 'success', message: '✅ DeerFlow 服务器已验证 ✓' }
          } else {
            self.testResult = { type: 'fail', message: '⛔ 非 DeerFlow 服务器，禁止使用' }
          }
        },
        fail: function(err) {
          var msg = err.errMsg || ''
          if (msg.indexOf('timeout') !== -1) {
            self.testResult = { type: 'fail', message: '❌ 连接超时（5秒），请检查地址或网络' }
          } else {
            self.testResult = { type: 'fail', message: '❌ 无法连接，请检查地址或网络' }
          }
        }
      })
    },

    retryLoad() {
      this.showErrorOverlay = false
      this.showWebView = true
      this.webViewError = ''

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
          var meta = D.querySelector('meta[name=viewport]')
          if (meta) {
            meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no'
          } else {
            var m = D.createElement('meta')
            m.name = 'viewport'
            m.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no'
            if (D.head) D.head.appendChild(m)
          }

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
          cs.textContent = '*{pointer-events:auto!important;-webkit-text-size-adjust:none!important}' +
            'html{touch-action:pan-y;-ms-touch-action:pan-y}' +
            'input,textarea,select,button,a{-webkit-user-select:text!important;user-select:text!important;touch-action:manipulation!important}'
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
.webview-container {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  padding-top: constant(safe-area-inset-top);
  padding-top: env(safe-area-inset-top);
}
.webview-hidden {
  pointer-events: none;
}
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
  margin-bottom: 12px;
}
.error-detail {
  width: 100%;
  font-size: 11px;
  color: #ee0a24;
  text-align: left;
  line-height: 1.4;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: #fef0f0;
  border-radius: 8px;
  word-break: break-all;
  max-height: 100px;
  overflow-y: auto;
}
.url-card {
  width: 100%;
  background: #f5f5f7;
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 16px;
  box-sizing: border-box;
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
  overflow-wrap: break-word;
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
  z-index: 9999;
}
.config-mask {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.4);
  z-index: 0;
}
.config-panel {
  width: 85%;
  max-width: 340px;
  background: #ffffff;
  border-radius: 16px;
  padding: 20px;
  position: relative;
  box-shadow: 0 4px 24px rgba(0,0,0,0.15);
  z-index: 1;
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

.log-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  margin-bottom: 4px;
}
.btn-log {
  flex: 1;
  text-align: center;
  padding: 10px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  background: #f0f5ff;
  color: #2b6cb0;
  border: 1px solid #bee3f8;
  box-sizing: border-box;
}
.btn-log-clear {
  flex: 1;
  text-align: center;
  padding: 10px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  background: #fff5f5;
  color: #c53030;
  border: 1px solid #fed7d7;
  box-sizing: border-box;
}

.loading-splash {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 9997;
  opacity: 0;
  animation: loadingFadeIn 0.2s ease-out forwards;
}

.loading-brand {
  width: 160px;
  height: auto;
  margin-bottom: 32px;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2.5px solid #e5e5ea;
  border-top-color: #007aff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}

.loading-text {
  font-size: 14px;
  color: #86868b;
  text-align: center;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes loadingFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
