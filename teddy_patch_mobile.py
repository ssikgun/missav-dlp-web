from pathlib import Path


INDEX = Path("templates/index.html")
MOBILE_STYLESHEET = '<link rel="stylesheet" href="/static/teddy-mobile.css">'


def replace_once(text, old, new, label):
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"mobile patch failed: {label} anchor count={count}")
    return text.replace(old, new, 1)


def main():
    text = INDEX.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '>\\u25b6 미리보기</button>',
        '>\\u25b6 재생</button>',
        "file playback label",
    )
    text = replace_once(
        text,
        "\\u2193 받기</a>' +\n                        '<button class=\"btn btn-ghost\" onclick=\"deleteTask(\\'' + id + '\\')\">\\u2715</button>'",
        "\\u2193 받기</a>' +\n                        '<button class=\"btn btn-danger\" onclick=\"deleteTask(\\'' + id + '\\')\">목록에서 삭제</button>'",
        "completed task remove action",
    )
    text = replace_once(
        text,
        "confirm('서버에서 파일을 삭제하시겠습니까?')",
        "confirm('이 파일을 NAS에서 삭제할까요? 삭제 후 되돌릴 수 없습니다.')",
        "NAS delete confirmation",
    )
    text = replace_once(
        text,
        '<video id="videoPlayer" controls></video>',
        '<video id="videoPlayer" controls playsinline preload="metadata"></video>',
        "mobile video attributes",
    )

    if MOBILE_STYLESHEET not in text:
        text = replace_once(
            text,
            "</head>",
            MOBILE_STYLESHEET + "</head>",
            "mobile stylesheet injection",
        )

    INDEX.write_text(text, encoding="utf-8")

    rendered = INDEX.read_text(encoding="utf-8")
    required = (
        '>\\u25b6 재생</button>',
        'class="btn btn-danger" onclick="deleteTask(',
        '>목록에서 삭제</button>',
        "이 파일을 NAS에서 삭제할까요? 삭제 후 되돌릴 수 없습니다.",
        'controls playsinline preload="metadata"',
        MOBILE_STYLESHEET,
    )
    missing = [marker for marker in required if marker not in rendered]
    if missing:
        raise SystemExit(f"mobile patch verification failed: {missing}")

    print("mobile UI patch: OK")


if __name__ == "__main__":
    main()
