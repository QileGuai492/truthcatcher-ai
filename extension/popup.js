(function() {
  const TRUTHCATCHER_URL = 'http://127.0.0.1:7860';

  function setStatus(msg) {
    var el = document.getElementById('status');
    if (el) el.textContent = msg;
  }

  // 加载当前页面 URL
  try {
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      var url = (tabs[0] && tabs[0].url) || '无法获取';
      var el = document.getElementById('urlDisplay');
      if (el) el.textContent = url;
    });
  } catch(e) { setStatus('加载失败: ' + e.message); }

  // 获取页面选中文字 → 填入下方文本框
  var btnSel = document.getElementById('btnGetSelection');
  if (btnSel) btnSel.addEventListener('click', async function() {
    setStatus('正在读取选中文字...');
    try {
      var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tabs[0]) { setStatus('未找到活动标签页'); return; }

      var results = await chrome.scripting.executeScript({
        target: { tabId: tabs[0].id },
        func: function() { return window.getSelection() ? window.getSelection().toString() : ''; }
      });

      var text = (results && results[0] && results[0].result) || '';
      if (text.length > 20) {
        var ta = document.getElementById('textInput');
        if (ta) ta.value = text;
        setStatus('已获取 ' + text.length + ' 字。确认后可点下方按钮打开分析。');
      } else {
        setStatus('未选中足够文字（仅' + text.length + '字）。请先在页面选中文章内容。');
      }
    } catch(e) {
      setStatus('读取失败: ' + (e.message || '权限不足，请刷新页面后重试'));
    }
  });

  // 打开 TruthCatcher
  var btnOpen = document.getElementById('btnOpenApp');
  if (btnOpen) btnOpen.addEventListener('click', function() {
    chrome.tabs.create({ url: TRUTHCATCHER_URL });
  });

  // 带上文本框文字打开 TruthCatcher
  var btnAnalyze = document.getElementById('btnAnalyzeText');
  if (btnAnalyze) btnAnalyze.addEventListener('click', function() {
    var text = document.getElementById('textInput').value.trim();
    if (!text) { setStatus('请先获取选中文字或手动粘贴内容'); return; }
    var url = TRUTHCATCHER_URL + '#text=' + encodeURIComponent(text);
    chrome.tabs.create({ url: url });
    setStatus('正在打开 TruthCatcher（' + text.length + ' 字）...');
  });

})();
