from pathlib import Path


APP = Path('app.py')
ENTRYPOINT = Path('teddy_entrypoint.py')


def replace_once(path, old, new, label):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one patch anchor, found {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def main():
    replace_once(
        APP,
        "from yt_dlp.extractor.common import InfoExtractor\n",
        "from yt_dlp.extractor.common import InfoExtractor\nfrom yt_dlp.utils import ExtractorError\n",
        'ExtractorError import',
    )

    replace_once(
        APP,
        """    def _real_extract(self, url):\n        video_id = self._match_id(url)\n        print(f'🔥 [로직 시작] 파싱 대상: {url}', flush=True)\n""",
        """    def _real_extract(self, url):\n        video_id = self._match_id(url)\n        print(f'🔥 [로직 시작] 파싱 대상: {url}', flush=True)\n\n        task_id = str((self._downloader.params or {}).get('teddy_task_id') or '')\n\n        def teddy_check_task_state():\n            if not task_id:\n                return\n            task = tasks.get(task_id)\n            if not task:\n                raise ExtractorError('Teddy task cancelled', expected=True)\n            if task.get('status') in ('일시정지 요청 중', '일시정지'):\n                raise ExtractorError('Teddy pause requested', expected=True)\n\n        teddy_check_task_state()\n""",
        'extraction task-state helper',
    )

    replace_once(
        APP,
        """        for mirror in mirrors:\n            test_url = f\"https://{mirror}{path}\"\n            proxy_list = [SPOOFDPI_PROXY, None] if settings.get('spoofdpi_enabled', True) else [None]\n            for proxy in proxy_list:\n                try:\n                    proxies = {\"https\": proxy, \"http\": proxy} if proxy else None\n                    res = cffi_requests.get(test_url, impersonate=\"chrome110\", timeout=20, proxies=proxies)\n                    if res.status_code == 200 and ('seek' in res.text or 'm3u8' in res.text):\n""",
        """        for mirror in mirrors:\n            teddy_check_task_state()\n            test_url = f\"https://{mirror}{path}\"\n            proxy_list = [SPOOFDPI_PROXY, None] if settings.get('spoofdpi_enabled', True) else [None]\n            for proxy in proxy_list:\n                teddy_check_task_state()\n                try:\n                    proxies = {\"https\": proxy, \"http\": proxy} if proxy else None\n                    res = cffi_requests.get(test_url, impersonate=\"chrome110\", timeout=20, proxies=proxies)\n                    teddy_check_task_state()\n                    if res.status_code == 200 and ('seek' in res.text or 'm3u8' in res.text):\n""",
        'pause checkpoints around page fetch',
    )

    replace_once(
        APP,
        """                except Exception as e:\n                    print(f'⚠️ {mirror} 접속 실패: {e}', flush=True)\n                    continue\n            if webpage:\n""",
        """                except ExtractorError:\n                    raise\n                except Exception as e:\n                    teddy_check_task_state()\n                    print(f'⚠️ {mirror} 접속 실패: {e}', flush=True)\n                    continue\n            teddy_check_task_state()\n            if webpage:\n""",
        'pause checkpoint after page fetch failure',
    )

    replace_once(
        APP,
        """            for tgt in IMPERSONATE_TARGETS:\n                try:\n                    h = {'Referer': referer, 'Origin': origin, **CROSS_SITE_HEADERS}\n""",
        """            for tgt in IMPERSONATE_TARGETS:\n                teddy_check_task_state()\n                try:\n                    h = {'Referer': referer, 'Origin': origin, **CROSS_SITE_HEADERS}\n""",
        'pause checkpoint before m3u8 fetch',
    )

    replace_once(
        APP,
        """                    r = cffi_requests.get(master_url, impersonate=tgt, timeout=15, headers=h)\n                    tag = 'm3u8+cf' if cookie else 'm3u8'\n""",
        """                    r = cffi_requests.get(master_url, impersonate=tgt, timeout=15, headers=h)\n                    teddy_check_task_state()\n                    tag = 'm3u8+cf' if cookie else 'm3u8'\n""",
        'pause checkpoint after m3u8 fetch',
    )

    replace_once(
        APP,
        """                except Exception as e:\n                    print(f'⚠️ m3u8 fetch ({tgt}) 실패: {e}', flush=True)\n            return None\n""",
        """                except ExtractorError:\n                    raise\n                except Exception as e:\n                    teddy_check_task_state()\n                    print(f'⚠️ m3u8 fetch ({tgt}) 실패: {e}', flush=True)\n            teddy_check_task_state()\n            return None\n""",
        'pause checkpoint after m3u8 failure',
    )

    replace_once(
        ENTRYPOINT,
        """        with core.yt_dlp.YoutubeDL(\n            {'quiet': True, 'no_warnings': True, 'proxy': None},\n            auto_init=False,\n        ) as ydl:\n""",
        """        with core.yt_dlp.YoutubeDL(\n            {\n                'quiet': True,\n                'no_warnings': True,\n                'proxy': None,\n                'teddy_task_id': task_id,\n            },\n            auto_init=False,\n        ) as ydl:\n""",
        'pass task id into custom extractor',
    )

    replace_once(
        ENTRYPOINT,
        """    except Exception as exc:\n        print(f'[Error] {url}: {exc}', flush=True)\n        if task_id in core.tasks:\n            core.tasks[task_id]['status'] = f'에러: {str(exc)[:100]}'\n            core.tasks[task_id]['speed_bps'] = 0\n            core.save_tasks()\n""",
        """    except Exception as exc:\n        task = core.tasks.get(task_id)\n        if task and task.get('status') in ('일시정지 요청 중', '일시정지'):\n            task['status'] = '일시정지'\n            task['speed_bps'] = 0\n            core.save_tasks()\n            print(f'[Pause] 추출 단계 일시정지 완료: {url}', flush=True)\n            return\n        print(f'[Error] {url}: {exc}', flush=True)\n        if task_id in core.tasks:\n            core.tasks[task_id]['status'] = f'에러: {str(exc)[:100]}'\n            core.tasks[task_id]['speed_bps'] = 0\n            core.save_tasks()\n""",
        'convert wrapped extractor pause into paused state',
    )

    print('MissAV extraction pause checkpoints runtime patch: OK')


if __name__ == '__main__':
    main()
