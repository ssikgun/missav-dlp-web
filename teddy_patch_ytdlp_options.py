from pathlib import Path


INDEX = Path('templates/index.html')
text = INDEX.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'yt-dlp options patch failed: {label}: expected 1 match, got {count}')
    text = text.replace(old, new, 1)


YT_DLP_SETTINGS = '''                <div class="setting-group teddy-ytdlp-settings">
                    <label class="setting-label">일반 사이트 yt-dlp 옵션</label>
                    <div class="setting-desc">YouTube 등 일반 사이트에 적용됩니다. 플레이리스트와 로그인/쿠키 기능은 포함하지 않습니다. 작업이 시작될 때 선택값을 작업에 고정해 재개 시에도 같은 옵션을 유지합니다.</div>

                    <div class="setting-group">
                        <label class="setting-label">다운로드 종류</label>
                        <select id="set-ytdlp-media-mode" class="setting-select">
                            <option value="video">영상 + 음성</option>
                            <option value="audio">오디오만</option>
                        </select>
                    </div>

                    <div id="teddy-ytdlp-video-options">
                        <div class="setting-group">
                            <label class="setting-label">최대 화질</label>
                            <select id="set-ytdlp-video-quality" class="setting-select">
                                <option value="best">최고 화질</option>
                                <option value="2160">2160p 이하</option>
                                <option value="1440">1440p 이하</option>
                                <option value="1080">1080p 이하</option>
                                <option value="720">720p 이하</option>
                                <option value="480">480p 이하</option>
                            </select>
                        </div>

                        <div class="setting-group">
                            <label class="setting-label">영상 컨테이너</label>
                            <select id="set-ytdlp-video-container" class="setting-select">
                                <option value="mp4">MP4 · 호환성 권장</option>
                                <option value="mkv">MKV · 코덱 호환 범위 넓음</option>
                            </select>
                        </div>

                        <div class="setting-group">
                            <label class="setting-label">자막 파일</label>
                            <div class="setting-desc">선택 언어의 일반 자막과 자동 생성 자막을 허용하며 영상과 별도 자막 파일로 저장합니다.</div>
                            <select id="set-ytdlp-subtitles" class="setting-select">
                                <option value="off">받지 않음</option>
                                <option value="ko">한국어</option>
                                <option value="en">영어</option>
                                <option value="ko_en">한국어 + 영어</option>
                            </select>
                        </div>
                    </div>

                    <div id="teddy-ytdlp-audio-options" style="display:none">
                        <div class="setting-group">
                            <label class="setting-label">오디오 형식</label>
                            <select id="set-ytdlp-audio-format" class="setting-select">
                                <option value="m4a">M4A · 기본</option>
                                <option value="mp3">MP3 · 192 kbps</option>
                            </select>
                        </div>
                    </div>
                </div>

'''

replace_once(
    '                <div class="setting-group teddy-routing-settings">',
    YT_DLP_SETTINGS + '                <div class="setting-group teddy-routing-settings">',
    'yt-dlp settings section before routing',
)

replace_once(
    "        video_quality: 'best',\n        auto_retry: true,",
    "        video_quality: 'best',\n        yt_dlp_media_mode: 'video',\n        yt_dlp_video_quality: 'best',\n        yt_dlp_video_container: 'mp4',\n        yt_dlp_audio_format: 'm4a',\n        yt_dlp_subtitles: 'off',\n        auto_retry: true,",
    'yt-dlp default settings',
)

replace_once(
    "            document.getElementById('set-quality').value = s.video_quality || 'best';",
    "            document.getElementById('set-quality').value = s.video_quality || 'best';\n            document.getElementById('set-ytdlp-media-mode').value = s.yt_dlp_media_mode || 'video';\n            document.getElementById('set-ytdlp-video-quality').value = s.yt_dlp_video_quality || 'best';\n            document.getElementById('set-ytdlp-video-container').value = s.yt_dlp_video_container || 'mp4';\n            document.getElementById('set-ytdlp-audio-format').value = s.yt_dlp_audio_format || 'm4a';\n            document.getElementById('set-ytdlp-subtitles').value = s.yt_dlp_subtitles || 'off';",
    'yt-dlp settings load',
)

replace_once(
    '            updateToggleText();',
    '            updateToggleText();\n            teddyUpdateYtDlpVisibility();',
    'yt-dlp visibility after settings load',
)

replace_once(
    "    document.getElementById('set-auto-retry').addEventListener('change', updateToggleText);\n",
    "    document.getElementById('set-auto-retry').addEventListener('change', updateToggleText);\n\n    function teddyUpdateYtDlpVisibility() {\n        const audioOnly = document.getElementById('set-ytdlp-media-mode').value === 'audio';\n        document.getElementById('teddy-ytdlp-video-options').style.display = audioOnly ? 'none' : '';\n        document.getElementById('teddy-ytdlp-audio-options').style.display = audioOnly ? '' : 'none';\n    }\n    document.getElementById('set-ytdlp-media-mode').addEventListener('change', teddyUpdateYtDlpVisibility);\n",
    'yt-dlp visibility controller',
)

replace_once(
    "            video_quality: document.getElementById('set-quality').value,\n            mirrors: mirrors,",
    "            video_quality: document.getElementById('set-quality').value,\n            yt_dlp_media_mode: document.getElementById('set-ytdlp-media-mode').value,\n            yt_dlp_video_quality: document.getElementById('set-ytdlp-video-quality').value,\n            yt_dlp_video_container: document.getElementById('set-ytdlp-video-container').value,\n            yt_dlp_audio_format: document.getElementById('set-ytdlp-audio-format').value,\n            yt_dlp_subtitles: document.getElementById('set-ytdlp-subtitles').value,\n            mirrors: mirrors,",
    'yt-dlp settings save',
)

INDEX.write_text(text, encoding='utf-8')
print('teddy yt-dlp options UI patch: OK')
