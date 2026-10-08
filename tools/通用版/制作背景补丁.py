"""为智码（ZCode）的程序包制作自定义对话背景补丁。

做什么：
  1. 读取 app.asar（Electron 程序包）；
  2. 在 out/renderer/index.html 的 </head> 前注入背景样式
     （深色模式半透明深色遮罩，浅色模式淡水印，侧边栏与卡片不受影响）；
  3. 把壁纸处理成 JPEG，作为 out/renderer/assets/zcode-custom-bg.jpg 加入包内；
  4. 重写包头索引，输出新程序包，并对包内全部文件逐字节核验。

输出（默认在脚本旁的「补丁输出」目录，两个文件必须放在一起）：
  app.asar.custom-bg   待安装的补丁程序包
  补丁信息.json        原版/补丁哈希等信息，供安装与恢复脚本校验

用法：
  python 制作背景补丁.py [--asar E:\\ZCode\\resources\\app.asar] [--image 壁纸.jpg] [--output 输出目录]
  省略参数时会自动探测智码安装位置；未给 --image 时先用仓库自带壁纸，
  找不到则弹出选图窗口。

依赖：Python 3.8+ 与 Pillow（pip install pillow）。
"""
from pathlib import Path
from PIL import Image, ImageOps
import argparse, copy, hashlib, io, json, os, struct, sys

INDEX_PATH = 'out/renderer/index.html'
ASSETS_DIR = 'out/renderer/assets'
IMAGE_NAME = 'zcode-custom-bg.jpg'
IMAGE_PATH = ASSETS_DIR + '/' + IMAGE_NAME
STYLE_ID = 'zcode-custom-bg'
BLOCK_SIZE = 4 * 1024 * 1024
SUPPORTED_ORIGINAL_HASHES = {
    "172d6f333e61642ce3882250949fafe8180f75b5b8e5552244ca2c59ca05d14e",
}

def file_hash(path):
    return digest_region(path, 0, path.stat().st_size).hex()

# 注入的背景样式（与本仓库补丁的已部署版本逐字节一致）
STYLE = (
    '<style id="zcode-custom-bg">\n'
    '/* Custom conversation background, 2026-10-08. Keep sidebar and cards unchanged. */\n'
    'section.bg-background:has([class~="@container/conversation"]) {\n'
    '  background-color: #0d0c12;\n'
    '  background-image:\n'
    '    linear-gradient(rgba(13,12,18,0.55), rgba(13,12,18,0.73)),\n'
    '    url("./assets/zcode-custom-bg.jpg");\n'
    '  background-repeat: no-repeat;\n'
    '  background-position: right center;\n'
    '  background-size: cover;\n'
    '}\n'
    'html:not(.dark) section.bg-background:has([class~="@container/conversation"]) {\n'
    '  background-color: #f4f4f5;\n'
    '  background-image:\n'
    '    linear-gradient(rgba(244,244,245,0.88), rgba(244,244,245,0.94)),\n'
    '    url("./assets/zcode-custom-bg.jpg");\n'
    '}\n'
    '</style>'
)

def read_archive(path):
    with open(path, 'rb') as f:
        raw = f.read(16)
        if len(raw) != 16:
            raise ValueError('程序包不完整。')
        first, header_size, payload_size, json_size = struct.unpack('<4I', raw)
        if first != 4 or header_size < 8 or header_size % 4 or payload_size + 4 != header_size or json_size > header_size - 8 or header_size > 64*1024*1024:
            raise ValueError('程序包格式不受支持。')
        text = f.read(json_size)
    if 8 + header_size > path.stat().st_size:
        raise ValueError('程序包头部长度不正确。')
    return json.loads(text), 8 + header_size

def entries(header):
    result = {}
    def walk(node, prefix=''):
        for name, child in node['files'].items():
            if '/' in name or '\\' in name or name in ('.', '..'):
                raise ValueError('程序包包含不安全路径。')
            path = prefix + name
            result[path] = child
            if 'files' in child:
                walk(child, path + '/')
    walk(header)
    return result

def packed_bytes(path, start, entry):
    if entry.get('unpacked') or 'offset' not in entry:
        raise ValueError('需要读取的资源不是包内普通文件。')
    offset, size = int(entry['offset']), entry['size']
    if offset < 0 or size < 0 or start + offset + size > path.stat().st_size:
        raise ValueError('程序包资源超出文件范围。')
    with open(path, 'rb') as f:
        f.seek(start + offset)
        return f.read(size)

def digest_region(path, start, size):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        f.seek(start)
        while size:
            block = f.read(min(size, BLOCK_SIZE))
            if not block:
                raise ValueError('文件读取不完整。')
            h.update(block)
            size -= len(block)
    return h.digest()

def integrity_of(content):
    # asar 惯例：空文件也记录一个「空内容哈希」分块
    blocks = [hashlib.sha256(content[i:i+BLOCK_SIZE]).hexdigest()
              for i in range(0, len(content), BLOCK_SIZE)] or [hashlib.sha256(b'').hexdigest()]
    return {'algorithm': 'SHA256', 'hash': hashlib.sha256(content).hexdigest(),
            'blockSize': BLOCK_SIZE, 'blocks': blocks}

def serialize_header(header):
    text = json.dumps(header, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    padding = b'\x00' * (-len(text) % 4)
    payload = struct.pack('<I', len(text)) + text + padding
    head_pickle = struct.pack('<I', len(payload)) + payload
    return struct.pack('<II', 4, len(head_pickle)) + head_pickle

def find_asar():
    candidates = []
    for drive in ('C:', 'D:', 'E:', 'F:'):
        candidates.append(drive + r'\ZCode\resources\app.asar')
    for env, sub in (('LocalAppData', r'Programs\ZCode\resources\app.asar'),
                     ('ProgramFiles', r'ZCode\resources\app.asar'),
                     ('ProgramFiles(x86)', r'ZCode\resources\app.asar')):
        base = os.environ.get(env)
        if base:
            candidates.append(os.path.join(base, sub))
    found = sorted({Path(c).resolve() for c in candidates if os.path.isfile(c)})
    return found[0] if len(found) == 1 else None

def default_image():
    folder = Path(__file__).resolve().parent
    candidates = [
        folder.parent.parent / 'assets' / '对话背景.jpg',
        folder / '对话背景.jpg',
        folder.parent / '对话背景.jpg',
        folder.parent / '素材' / '对话背景.jpg',
    ]
    return next((path for path in candidates if path.is_file()), None)

def choose_image():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        selected = filedialog.askopenfilename(title='选择对话壁纸', filetypes=[('常见图片', '*.jpg *.jpeg *.png *.webp *.bmp'), ('全部文件', '*.*')])
    finally:
        root.destroy()
    return Path(selected) if selected else None

def load_image_bytes(image):
    with Image.open(image) as original:
        converted = ImageOps.exif_transpose(original).convert('RGBA')
        converted.thumbnail((3840, 3840), Image.Resampling.LANCZOS)
        if converted.width < 32 or converted.height < 32:
            raise ValueError('图片太小，请选择正常尺寸的图片。')
        canvas = Image.new('RGB', converted.size, '#0d0c12')
        canvas.paste(converted, mask=converted.getchannel('A'))
        encoded = io.BytesIO()
        canvas.save(encoded, 'JPEG', quality=94, optimize=True)
        content = encoded.getvalue()
    Image.open(io.BytesIO(content)).verify()
    return content

def verify_entries(path, start, mapping):
    checked = 0
    for p, entry in mapping.items():
        if 'files' in entry or 'link' in entry or entry.get('unpacked') or 'integrity' not in entry:
            continue
        data = packed_bytes(path, start, entry)
        integ = entry['integrity']
        if integ.get('algorithm') != 'SHA256':
            raise ValueError('不支持的完整性算法：' + p)
        if hashlib.sha256(data).hexdigest() != str(integ['hash']).lower():
            raise ValueError('完整性校验失败：' + p)
        blocks = integ.get('blocks')
        if blocks:
            size = integ['blockSize']
            if data:
                actual = [hashlib.sha256(data[i:i+size]).hexdigest() for i in range(0, len(data), size)]
            else:
                actual = [hashlib.sha256(b'').hexdigest()]
            if actual != [str(b).lower() for b in blocks]:
                raise ValueError('分块校验失败：' + p)
        checked += 1
        if checked % 5000 == 0:
            print('  已核验 {} 个文件…'.format(checked))
    return checked

def _make_patch(asar, image, out_dir):
    out_path = out_dir / 'app.asar.custom-bg'
    info_path = out_dir / '补丁信息.json'
    if out_path.exists() or info_path.exists():
        raise ValueError('输出目录里已有上次的结果。为避免混淆，请先清空「补丁输出」目录再运行。')

    original_hash = file_hash(asar)
    if original_hash not in SUPPORTED_ORIGINAL_HASHES:
        raise ValueError('尚未验证此版本，或该程序包已修改。为避免无效背景或启动失败，已停止制作。请先恢复同版本原版，升级后的版本需重新适配。')
    header, old_start = read_archive(asar)
    original = entries(header)
    if IMAGE_PATH in original:
        raise ValueError('这个程序包已经带背景补丁。换图请用「更换壁纸」，或先用「恢复原版」。')
    idx = original.get(INDEX_PATH)
    assets = original.get(ASSETS_DIR)
    if not idx or idx.get('unpacked') or 'offset' not in idx:
        raise ValueError('未找到可修改的界面入口，版本可能不受支持。')
    if not assets or 'files' not in assets:
        raise ValueError('未找到资源目录，版本可能不受支持。')
    html = packed_bytes(asar, old_start, idx)
    if STYLE_ID.encode('utf-8') in html:
        raise ValueError('这个程序包已经带背景补丁。换图请用「更换壁纸」，或先用「恢复原版」。')
    if html.count(b'</head>') != 1:
        raise ValueError('界面文件结构与预期不同，可能是不兼容的版本。')

    new_html = html.replace(b'</head>', STYLE.encode('utf-8') + b'\n</head>', 1)
    image_bytes = load_image_bytes(image)
    print('壁纸已处理：{} 字节（联合图像专家组格式，质量 94）'.format(len(image_bytes)))

    old_length = asar.stat().st_size - old_start
    new_header = copy.deepcopy(header)
    new_entries = entries(new_header)
    new_entries[INDEX_PATH]['offset'] = str(old_length)
    new_entries[INDEX_PATH]['size'] = len(new_html)
    new_entries[INDEX_PATH]['integrity'] = integrity_of(new_html)
    new_entries[ASSETS_DIR]['files'][IMAGE_NAME] = {
        'size': len(image_bytes),
        'offset': str(old_length + len(new_html)),
        'integrity': integrity_of(image_bytes),
    }
    prefix = serialize_header(new_header)

    print('正在写出补丁程序包（约 {} MB）…'.format((old_length + len(new_html) + len(image_bytes)) // 1048576 + 1))
    with open(asar, 'rb') as source, open(out_path, 'xb') as output:
        output.write(prefix)
        source.seek(old_start)
        while block := source.read(BLOCK_SIZE):
            output.write(block)
        output.write(new_html)
        output.write(image_bytes)

    print('正在核验补丁结构…')
    v_header, v_start = read_archive(out_path)
    v_entries = entries(v_header)
    if set(v_entries) != set(original) | {IMAGE_PATH}:
        raise ValueError('补丁包文件清单与预期不一致。')
    for p, entry in original.items():
        if p == INDEX_PATH or 'files' in entry:
            continue
        if v_entries[p] != entry:
            raise ValueError('其他文件的元数据发生变化：' + p)
    if digest_region(asar, old_start, old_length) != digest_region(out_path, v_start, old_length):
        raise ValueError('原程序内容校验失败。')
    if packed_bytes(out_path, v_start, v_entries[INDEX_PATH]) != new_html:
        raise ValueError('注入后的界面文件校验失败。')
    if packed_bytes(out_path, v_start, v_entries[IMAGE_PATH]) != image_bytes:
        raise ValueError('壁纸内容校验失败。')

    print('正在逐文件核验补丁包（含未改动的全部包内文件）…')
    checked = verify_entries(out_path, v_start, v_entries)

    if file_hash(asar) != original_hash:
        raise ValueError('制作期间原程序被修改，补丁作废。请退出应用和更新程序后重试。')
    info = {
        'schemaVersion': 1,
        'originalHash': original_hash,
        'patchedHash': file_hash(out_path),
        'patchedFile': out_path.name,
        'imageName': image.name,
        'generatedAt': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
        'filesOriginal': sum(1 for e in original.values() if 'files' not in e),
        'filesPatched': sum(1 for e in v_entries.values() if 'files' not in e),
        'integrityVerifiedFiles': checked,
    }
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print()
    print('补丁制作完成，全部校验通过（逐文件核验 {} 个）。'.format(checked))
    print('  补丁程序包：{}'.format(out_path))
    print('  补丁信息：{}'.format(info_path))
    print('下一步：彻底退出智码后，运行同目录的「安装背景补丁」工具。')

def make_patch(asar, image, out_dir):
    paths = [out_dir / 'app.asar.custom-bg', out_dir / '补丁信息.json']
    if any(p.exists() for p in paths):
        raise ValueError('输出目录已有结果，请改用新的空目录，避免覆盖已有补丁。')
    # 目录级排他锁避免两个制作进程互相清理输出。
    lock = out_dir / '.制作中.lock'
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(str(os.getpid()))
    try:
        _make_patch(asar, image, out_dir)
    except Exception:
        for p in paths:
            if p.is_file():
                p.unlink()
        raise
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='为智码制作自定义对话背景补丁')
    parser.add_argument('--asar', help='app.asar 路径（默认自动探测智码安装位置）')
    parser.add_argument('--image', help='壁纸图片路径（默认用仓库自带壁纸，否则弹窗选择）')
    parser.add_argument('--output', help='输出目录（默认为脚本旁的「补丁输出」）')
    args = parser.parse_args()

    asar = Path(args.asar) if args.asar else find_asar()
    if asar is None:
        print('未找到智码的程序包。请用 --asar 指定 app.asar 的完整路径。')
        sys.exit(1)
    if not asar.is_file():
        print('指定的程序包不存在：' + str(asar))
        sys.exit(1)

    image = Path(args.image) if args.image else default_image()
    if image is None:
        image = choose_image()
    if image is None:
        print('已取消选图，未生成补丁。')
        sys.exit(10)
    if not image.is_file():
        print('指定的图片不存在：' + str(image))
        sys.exit(1)

    out_dir = Path(args.output) if args.output else Path(__file__).resolve().parent / '补丁输出'
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        make_patch(asar, image, out_dir)
    except Exception as error:
        print('未完成制作：' + str(error))
        sys.exit(1)

if __name__ == '__main__':
    main()
