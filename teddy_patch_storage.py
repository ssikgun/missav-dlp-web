import hashlib
from pathlib import Path


INDEX = Path('templates/index.html')
text = INDEX.read_text(encoding='utf-8')
FINAL_INDEX_SHA256 = '84609dc23a2c3583bd099a6a2f0ed7e2301bb7645321e087b73595cb88326563'
IS_FINAL_INDEX = hashlib.sha256(INDEX.read_bytes()).hexdigest() == FINAL_INDEX_SHA256


def replace_once(old, new, label):
    global text
    if IS_FINAL_INDEX:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'storage patch failed: {label}: expected 1 match, got {count}')
    text = text.replace(old, new, 1)


replace_once(
    '    // --- Files ---\n    let allFiles = [];',
    '''    function teddyEncodeFilePath(name) {
        return String(name || '').split('/').map(encodeURIComponent).join('/');
    }

    // --- Files ---
    let allFiles = [];''',
    'file path encoder',
)

replace_once(
    "'<a class=\"btn btn-primary\" href=\"/api/files/' + encodeURIComponent(task.filename) + '/download\" style=\"text-decoration:none\">↓ 받기</a>' +",
    "'<a class=\"btn btn-primary\" href=\"/api/files/' + teddyEncodeFilePath(task.filename) + '/download\" style=\"text-decoration:none\">↓ 받기</a>' +",
    'completed task download path',
)

replace_once(
    '            const encodedName = encodeURIComponent(f.name);',
    '            const encodedName = teddyEncodeFilePath(f.name);',
    'file manager nested path',
)

INDEX.write_text(text, encoding='utf-8')
print('teddy storage UI patch: OK')
