const DOWNLOADER_ENDPOINT = 'http://missav-dlp-web:5000/download';
const DEFAULT_TITLE = '현재 페이지 다운로드';

function setActionIcon() {
  try {
    const sizes = [16, 32];
    const imageData = {};

    for (const size of sizes) {
      const canvas = new OffscreenCanvas(size, size);
      const ctx = canvas.getContext('2d');
      const scale = size / 16;

      ctx.clearRect(0, 0, size, size);
      ctx.strokeStyle = '#2563eb';
      ctx.lineWidth = Math.max(1.6, 2 * scale);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';

      ctx.beginPath();
      ctx.moveTo(8 * scale, 2.5 * scale);
      ctx.lineTo(8 * scale, 10 * scale);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(4.5 * scale, 7 * scale);
      ctx.lineTo(8 * scale, 10.5 * scale);
      ctx.lineTo(11.5 * scale, 7 * scale);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(3.5 * scale, 13 * scale);
      ctx.lineTo(12.5 * scale, 13 * scale);
      ctx.stroke();

      imageData[String(size)] = ctx.getImageData(0, 0, size, size);
    }

    chrome.action.setIcon({ imageData }).catch(() => {});
  } catch (_) {
    // The extension remains usable even if a platform cannot render the custom icon.
  }
}

async function flashResult(text, title, color, durationMs = 2200) {
  try {
    await chrome.action.setBadgeBackgroundColor({ color });
    await chrome.action.setBadgeText({ text });
    await chrome.action.setTitle({ title });
  } catch (_) {}

  setTimeout(() => {
    chrome.action.setBadgeText({ text: '' }).catch(() => {});
    chrome.action.setTitle({ title: DEFAULT_TITLE }).catch(() => {});
  }, durationMs);
}

async function showPageToast(tabId, kind, message, durationMs = 3200) {
  if (!Number.isInteger(tabId)) return;

  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: (toastKind, toastMessage, timeoutMs) => {
        const TOAST_ID = '__teddy_downloader_toast__';
        const palette = {
          info: { bg: '#2563eb', border: '#60a5fa' },
          success: { bg: '#15803d', border: '#4ade80' },
          warning: { bg: '#b45309', border: '#fbbf24' },
          error: { bg: '#b91c1c', border: '#f87171' },
        };
        const colors = palette[toastKind] || palette.info;

        let toast = document.getElementById(TOAST_ID);
        if (!toast) {
          toast = document.createElement('div');
          toast.id = TOAST_ID;
          toast.setAttribute('role', 'status');
          toast.style.position = 'fixed';
          toast.style.top = '22px';
          toast.style.right = '22px';
          toast.style.zIndex = '2147483647';
          toast.style.maxWidth = '420px';
          toast.style.padding = '12px 16px';
          toast.style.borderRadius = '10px';
          toast.style.color = '#fff';
          toast.style.font = '600 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
          toast.style.boxShadow = '0 12px 30px rgba(0,0,0,.28)';
          toast.style.pointerEvents = 'none';
          toast.style.opacity = '0';
          toast.style.transform = 'translateY(-8px)';
          toast.style.transition = 'opacity .16s ease, transform .16s ease';
          document.documentElement.appendChild(toast);
        }

        toast.textContent = toastMessage;
        toast.style.background = colors.bg;
        toast.style.border = `1px solid ${colors.border}`;
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-8px)';

        requestAnimationFrame(() => {
          toast.style.opacity = '1';
          toast.style.transform = 'translateY(0)';
        });

        if (window.__teddyDownloaderToastTimer) {
          clearTimeout(window.__teddyDownloaderToastTimer);
        }
        window.__teddyDownloaderToastTimer = setTimeout(() => {
          toast.style.opacity = '0';
          toast.style.transform = 'translateY(-8px)';
          setTimeout(() => toast.remove(), 220);
        }, Math.max(900, Number(timeoutMs) || 3200));
      },
      args: [kind, String(message || ''), durationMs],
    });
  } catch (error) {
    // The badge still provides feedback on pages that Chromium forbids scripting.
    console.warn('[Teddy Downloader] page toast unavailable:', error);
  }
}

function routeLabel(mode) {
  const value = String(mode || '').toLowerCase();
  if (value === 'vpn') return 'VPN';
  if (value === 'proxy') return 'Proxy';
  if (value === 'direct') return 'Direct';
  return 'Auto';
}

async function enqueueCurrentTab(tab) {
  const rawUrl = String(tab && tab.url ? tab.url : '').trim();
  if (!rawUrl) {
    throw new Error('현재 탭 URL을 읽을 수 없습니다.');
  }

  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch (_) {
    throw new Error('올바른 URL이 아닙니다.');
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('http/https 페이지에서만 사용할 수 있습니다.');
  }

  await showPageToast(tab.id, 'info', '⬇ 다운로드 요청 중…', 10000);

  const response = await fetch(DOWNLOADER_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
    },
    body: new URLSearchParams({
      url: rawUrl,
      network_mode: 'auto'
    }).toString()
  });

  let payload = {};
  try {
    payload = await response.json();
  } catch (_) {}

  if (response.status === 409 && payload.status === 'duplicate') {
    const message = payload.message || '이미 다운로드 큐에 있는 항목입니다.';
    await flashResult('DUP', message, '#d97706', 3000);
    await showPageToast(tab.id, 'warning', `⚠ ${message}`, 3800);
    return { status: 'duplicate', payload };
  }

  if (!response.ok || payload.status !== 'success') {
    const message = payload.message || `Downloader 응답 오류 (${response.status})`;
    throw new Error(message);
  }

  const route = routeLabel(payload.network_mode);
  await flashResult('OK', `큐 추가 완료 · ${route}`, '#16a34a');
  await showPageToast(tab.id, 'success', `✅ 다운로드 큐에 추가했습니다 · ${route}`, 3400);
  return { status: 'success', payload };
}

chrome.runtime.onInstalled.addListener(() => {
  setActionIcon();
  chrome.action.setTitle({ title: DEFAULT_TITLE }).catch(() => {});
});

chrome.runtime.onStartup.addListener(() => {
  setActionIcon();
});

setActionIcon();

chrome.action.onClicked.addListener(async (tab) => {
  try {
    await enqueueCurrentTab(tab);
  } catch (error) {
    const message = error && error.message ? error.message : '다운로드 큐 추가 실패';
    console.error('[Teddy Downloader]', message);
    await flashResult('!', message, '#dc2626', 3200);
    await showPageToast(tab && tab.id, 'error', `❌ ${message}`, 4200);
  }
});
