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

async function flashResult(text, title, color) {
  try {
    await chrome.action.setBadgeBackgroundColor({ color });
    await chrome.action.setBadgeText({ text });
    await chrome.action.setTitle({ title });
  } catch (_) {}

  setTimeout(() => {
    chrome.action.setBadgeText({ text: '' }).catch(() => {});
    chrome.action.setTitle({ title: DEFAULT_TITLE }).catch(() => {});
  }, 1800);
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

  if (!response.ok || payload.status !== 'success') {
    const message = payload.message || `Downloader 응답 오류 (${response.status})`;
    throw new Error(message);
  }

  const route = payload.network_mode ? String(payload.network_mode).toUpperCase() : 'AUTO';
  await flashResult('OK', `큐 추가 완료 · ${route}`, '#16a34a');
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
    await flashResult('!', message, '#dc2626');
  }
});
