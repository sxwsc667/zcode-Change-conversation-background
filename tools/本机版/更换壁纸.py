"""仅替换已安装背景补丁中的图片；其他文件保持原样。"""
from pathlib import Path
from PIL import Image, ImageOps
import copy, hashlib, io, json, struct, sys

IMAGE_PATH = 'out/renderer/assets/zcode-custom-bg.jpg'
INDEX_PATH = 'out/renderer/index.html'

def read_archive(path):
    with open(path, 'rb') as f:
        raw = f.read(16)
        if len(raw) != 16:
            raise ValueError('程序包不完整。')
        first, header_size, payload_size, json_size = struct.unpack('<4I', raw)
        if first != 4 or payload_size + 4 != header_size or json_size > header_size - 8 or header_size > 64*1024*1024:
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
        raise ValueError('需要修改的资源不是包内普通文件。')
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
            block = f.read(min(size, 4*1024*1024))
            if not block:
                raise ValueError('文件读取不完整。')
            h.update(block)
            size -= len(block)
    return h.digest()

def choose_image():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        selected = filedialog.askopenfilename(title='选择新的对话壁纸', filetypes=[('常见图片', '*.jpg *.jpeg *.png *.webp *.bmp'), ('全部文件', '*.*')])
    finally:
        root.destroy()
    return Path(selected) if selected else None

def replace_wallpaper(source, destination, image):
    if destination.exists() or source.resolve() == destination.resolve():
        raise ValueError('输出文件已存在或与原文件相同，停止操作。')
    header, old_start = read_archive(source)
    original_entries = entries(header)
    if IMAGE_PATH not in original_entries or INDEX_PATH not in original_entries:
        raise ValueError('当前程序没有安装本次背景补丁，请先运行安装对话背景工具。')
    html = packed_bytes(source, old_start, original_entries[INDEX_PATH]).decode('utf-8')
    if '<style id="zcode-custom-bg">' not in html or 'section.bg-background:has([class~="@container/conversation"])' not in html:
        raise ValueError('当前程序的背景补丁版本不同，停止操作。')
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
    old_length = source.stat().st_size - old_start
    new_header = copy.deepcopy(header)
    record = entries(new_header)[IMAGE_PATH]
    record['offset'] = str(old_length)
    record['size'] = len(content)
    block_size = 4*1024*1024
    record['integrity'] = {'algorithm': 'SHA256', 'hash': hashlib.sha256(content).hexdigest(), 'blockSize': block_size, 'blocks': [hashlib.sha256(content[i:i+block_size]).hexdigest() for i in range(0, len(content), block_size)]}
    text = json.dumps(new_header, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    padding = b'\x00' * (-len(text) % 4)
    payload = struct.pack('<I', len(text)) + text + padding
    head_pickle = struct.pack('<I', len(payload)) + payload
    prefix = struct.pack('<II', 4, len(head_pickle)) + head_pickle
    with open(source, 'rb') as original, open(destination, 'xb') as output:
        output.write(prefix)
        original.seek(old_start)
        while block := original.read(4*1024*1024):
            output.write(block)
        output.write(content)
    checked_header, checked_start = read_archive(destination)
    checked_entries = entries(checked_header)
    if original_entries.keys() != checked_entries.keys() or any(original_entries[p] != checked_entries[p] for p in original_entries if p != IMAGE_PATH and 'files' not in original_entries[p]):
        raise ValueError('其他文件的元数据发生变化，停止安装。')
    if digest_region(source, old_start, old_length) != digest_region(destination, checked_start, old_length):
        raise ValueError('原程序内容校验失败，停止安装。')
    if packed_bytes(destination, checked_start, checked_entries[IMAGE_PATH]) != content:
        raise ValueError('新壁纸内容校验失败，停止安装。')
    Image.open(io.BytesIO(content)).verify()
    print('新壁纸已写入临时程序包，其他程序内容校验通过。')

if __name__ == '__main__':
    try:
        source, destination = Path(sys.argv[1]), Path(sys.argv[2])
        image = Path(sys.argv[3]) if len(sys.argv) > 3 else choose_image()
        if image is None:
            print('已取消选图，没有修改当前程序。')
            sys.exit(10)
        replace_wallpaper(source, destination, image)
    except Exception as error:
        print('未完成更换：' + str(error))
        sys.exit(1)
