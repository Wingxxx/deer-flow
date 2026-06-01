# QR Code 工具页 — URL 输入 + 防抖自动生成 Implementation Plan

> **For agentic workers:** This is a single-file modification task. Inline execution.

**Goal:** 改造 `qr-code.html`，从硬编码 URL 展示页变为用户可手动输入 URL、防抖自动生成二维码的工具页面。

**Architecture:** 保持纯静态单 HTML 文件，不引入任何构建工具或额外依赖。利用现有 `qrcodejs` CDN 库，通过防抖（debounce 600ms）监听 input 事件实现输入完成后自动更新二维码。同时保留「生成」按钮作为手动触发兜底。

**Tech Stack:** HTML5 + CSS3 + Vanilla JS + qrcodejs CDN

---

### Task 1: 改造 qr-code.html

**Files:**
- Modify: `d:\Wing_D\emto\2026\2026.5\uni-app\qr-code.html`（全文重写）

#### 具体改动点

1. **HTML 结构改动：**
   - 标题改为通用「二维码生成器」
   - 副标题改为「输入 URL 自动生成二维码」
   - 在卡片顶部添加输入框区域：`<input type="url">` + 「生成」按钮
   - 二维码容器保留 `#qrcode`
   - URL 展示区改为动态显示当前编码的 URL
   - 提示文字改为动态状态提示（输入中/空/已生成）

2. **CSS 新增样式：**
   - 输入框样式：圆角边框、聚焦高亮、等宽字体
   - 按钮样式：主色填充圆角按钮
   - 空状态提示样式：居中灰色文字
   - 响应式适配

3. **JavaScript 逻辑：**
   - 维护单个 QRCode 实例，复用 `clear()` + `makeCode()` 方法
   - 输入框 `input` 事件绑定 600ms 防抖（debounce）
   - 「生成」按钮点击立即生成（取消防抖定时器）
   - 输入为空时清除二维码，显示「请输入 URL」提示
   - 粘贴事件同样触发防抖（`input` 事件已涵盖）
   - 二维码生成失败时错误捕获

#### 具体代码

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>二维码生成器</title>
<style>
body {
  margin: 0;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #f5f5f7;
  font-family: -apple-system, system-ui, sans-serif;
}
.card {
  background: #fff;
  border-radius: 20px;
  padding: 40px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.1);
  text-align: center;
  max-width: 420px;
  width: 90%;
}
.card h1 {
  font-size: 22px;
  color: #1d1d1f;
  margin: 0 0 4px;
}
.card .subtitle {
  font-size: 14px;
  color: #86868b;
  margin-bottom: 24px;
}
.input-row {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}
.input-row input {
  flex: 1;
  padding: 10px 14px;
  border: 2px solid #e5e5ea;
  border-radius: 10px;
  font-size: 15px;
  font-family: monospace;
  outline: none;
  transition: border-color 0.2s;
}
.input-row input:focus {
  border-color: #07c160;
}
.input-row input::placeholder {
  color: #aeaeb2;
  font-family: -apple-system, system-ui, sans-serif;
}
.input-row button {
  padding: 10px 20px;
  background: #07c160;
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.2s;
}
.input-row button:hover {
  background: #06b156;
}
.input-row button:active {
  background: #059a4c;
}
.qr-wrapper {
  display: inline-block;
  padding: 16px;
  background: #fff;
  border-radius: 12px;
  border: 2px solid #e5e5ea;
  min-width: 220px;
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.qr-wrapper canvas, .qr-wrapper img {
  display: block;
  max-width: 100%;
}
.qr-placeholder {
  color: #aeaeb2;
  font-size: 14px;
}
.url-display {
  margin-top: 16px;
  padding: 10px 16px;
  background: #f5f5f7;
  border-radius: 10px;
  font-size: 14px;
  color: #1d1d1f;
  word-break: break-all;
  font-family: monospace;
  min-height: 20px;
}
.status-hint {
  margin-top: 12px;
  font-size: 13px;
  font-weight: 500;
  min-height: 20px;
}
.status-hint.idle {
  color: #aeaeb2;
}
.status-hint.success {
  color: #07c160;
}
.status-hint.error {
  color: #ff3b30;
}
</style>
</head>
<body>
<div class="card">
  <h1>二维码生成器</h1>
  <div class="subtitle">输入 URL 自动生成二维码</div>

  <div class="input-row">
    <input type="url" id="urlInput" placeholder="请输入 URL，例如 http://192.168.1.56:2026/" autofocus>
    <button id="generateBtn">生成</button>
  </div>

  <div class="qr-wrapper" id="qrWrapper">
    <div id="qrcode"></div>
    <div class="qr-placeholder" id="placeholder">请输入 URL</div>
  </div>

  <div class="url-display" id="urlDisplay"></div>
  <div class="status-hint idle" id="statusHint">等待输入…</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
<script>
(function() {
  var qrInput = document.getElementById('urlInput');
  var generateBtn = document.getElementById('generateBtn');
  var qrContainer = document.getElementById('qrcode');
  var placeholder = document.getElementById('placeholder');
  var urlDisplay = document.getElementById('urlDisplay');
  var statusHint = document.getElementById('statusHint');
  var qrInstance = null;
  var debounceTimer = null;
  var DEBOUNCE_DELAY = 600;

  function setStatus(text, type) {
    statusHint.textContent = text;
    statusHint.className = 'status-hint ' + type;
  }

  function generateQR(url) {
    if (!url || url.trim() === '') {
      if (qrInstance) {
        qrInstance.clear();
        qrInstance = null;
      }
      placeholder.style.display = 'block';
      urlDisplay.textContent = '';
      setStatus('请输入 URL', 'idle');
      return;
    }

    var trimmedUrl = url.trim();

    try {
      if (qrInstance) {
        qrInstance.clear();
        qrInstance.makeCode(trimmedUrl);
      } else {
        qrInstance = new QRCode(qrContainer, {
          text: trimmedUrl,
          width: 220,
          height: 220,
          colorDark: '#1d1d1f',
          colorLight: '#ffffff',
          correctLevel: QRCode.CorrectLevel.H
        });
      }
      placeholder.style.display = 'none';
      urlDisplay.textContent = trimmedUrl;
      setStatus('✅ 二维码已生成', 'success');
    } catch (e) {
      setStatus('❌ 生成失败：' + e.message, 'error');
    }
  }

  function debouncedGenerate() {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    debounceTimer = setTimeout(function() {
      generateQR(qrInput.value);
      debounceTimer = null;
    }, DEBOUNCE_DELAY);
  }

  qrInput.addEventListener('input', function() {
    setStatus('等待输入完成…', 'idle');
    if (qrInput.value.trim() === '') {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
        debounceTimer = null;
      }
      generateQR('');
    } else {
      debouncedGenerate();
    }
  });

  generateBtn.addEventListener('click', function() {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
    generateQR(qrInput.value);
  });

  qrInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
        debounceTimer = null;
      }
      generateQR(qrInput.value);
    }
  });
})();
</script>
</body>
</html>
```

#### 关键设计说明

- **防抖机制**：`input` 事件触发时启动 600ms 定时器，持续输入则不断重置，停止输入后才生成二维码
- **输入清空**：当输入框为空时，立即清除二维码（不清防抖，直接执行）
- **Enter 键**：按回车立即生成，无视防抖
- **「生成」按钮**：点击立即生成，取消未执行的防抖定时器
- **实例复用**：首次用 `new QRCode()` 创建实例，后续用 `clear()` + `makeCode()` 复用，避免 DOM 中重复创建 canvas 元素
- **占位符控制**：无二维码时显示「请输入 URL」占位文字，有二维码时隐藏
