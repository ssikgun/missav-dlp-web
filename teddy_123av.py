import json
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError


class Teddy123AVIE(InfoExtractor):
    IE_NAME = 'teddy_123av'

    _VALID_URL = (
        r'https?://(?:www\.)?123av\.com/'
        r'(?:[^/?#]+/)*v/(?P<id>[^/?#]+)'
    )

    def _real_extract(self, url):
        video_id = self._match_id(url)

        webpage = self._download_webpage(
            url,
            video_id,
            note='Downloading 123AV page',
        )

        escaped = self._search_regex(
            r'''x-data="player\(JSON\.parse\('([^']+)'\)''',
            webpage,
            'episode data',
        )

        try:
            episode_json = json.loads(f'"{escaped}"')
            episodes = json.loads(episode_json)
        except Exception as exc:
            raise ExtractorError(
                f'123AV episode data parse failed: {exc}'
            )

        if not isinstance(episodes, list) or not episodes:
            raise ExtractorError(
                '123AV has no playable episodes'
            )

        player_url = ''

        for episode in episodes:
            if not isinstance(episode, dict):
                continue

            candidate = str(
                episode.get('url') or ''
            )

            if candidate.startswith(
                'https://javplayer.cc/e/'
            ):
                player_url = candidate
                break

        if not player_url:
            raise ExtractorError(
                '123AV javplayer URL not found'
            )

        parsed = urlsplit(player_url)

        player_id = (
            parsed.path.rstrip('/')
            .rsplit('/', 1)[-1]
        )

        if not player_id:
            raise ExtractorError(
                'javplayer ID not found'
            )

        query = [
            (key, value)
            for key, value in parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
            if key != 'id'
        ]

        query.append(('id', player_id))

        stream_api = urlunsplit((
            parsed.scheme,
            parsed.netloc,
            '/stream',
            urlencode(query),
            '',
        ))

        player_page = urlunsplit((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            '',
            '',
        ))
        player_origin = (
            f'{parsed.scheme}://{parsed.netloc}'
        )

        api_headers = {
            'Referer': player_page,
        }

        payload = self._download_json(
            stream_api,
            video_id,
            note='Resolving javplayer stream',
            headers=api_headers,
        )

        media = (
            payload.get('media')
            if isinstance(payload, dict)
            else None
        )

        if not isinstance(media, dict):
            raise ExtractorError(
                'javplayer media object missing'
            )

        stream_url = str(
            media.get('stream') or ''
        )

        stream_parts = urlsplit(stream_url)

        if (
            stream_parts.scheme != 'https'
            or not stream_parts.hostname
        ):
            raise ExtractorError(
                'javplayer returned invalid stream URL'
            )

        hls_headers = {
            'Referer': player_page,
            'Origin': player_origin,
        }

        formats, subtitles = (
            self._extract_m3u8_formats_and_subtitles(
                stream_url,
                video_id,
                'mp4',
                m3u8_id='hls',
                headers=hls_headers,
            )
        )

        # yt-dlp may not preserve extractor-time manifest headers on each
        # returned HLS format. wowstream requires a javplayer Referer or
        # Origin on the variant/segment requests, so make that boundary
        # explicit on every format handed to the native HLS downloader.
        for fmt in formats:
            fmt_headers = fmt.setdefault(
                'http_headers',
                {},
            )
            fmt_headers.update(hls_headers)

        for entries in subtitles.values():
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                sub_headers = entry.setdefault(
                    'http_headers',
                    {},
                )
                sub_headers.update(hls_headers)

        title = self._html_search_regex(
            r'<h1[^>]*class="watch__title"[^>]*>'
            r'(.*?)</h1>',
            webpage,
            'title',
            default=video_id,
        )

        thumbnail = self._og_search_thumbnail(
            webpage,
            default=None,
        )

        return {
            'id': video_id,
            'title': title,
            'thumbnail': thumbnail,
            'formats': formats,
            'subtitles': subtitles,
            'age_limit': 18,
        }
