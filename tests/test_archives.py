"""程序包制作与换图回归测试；只操作临时目录。"""
import contextlib, copy, hashlib, importlib.util, io, json, struct, tempfile, unittest
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'tools'/'通用版'
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,TOOLS/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
patch=load('patch','制作背景补丁.py')
swap=load('swap','更换壁纸.py')
class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'original.asar';self.image=self.root/'image.png'
        Image.new('RGBA',(96,64),(200,100,20,170)).save(self.image)
        self.header={'files':{}}
        payload=bytearray()
        for name,data in [('out/renderer/index.html',b'<!doctype html><html><head></head><body>test</body></html>'),('out/renderer/assets/main.js',b'untouched program'),('empty.txt',b'')]:
            parent=self.header
            parts=name.split('/')
            for part in parts[:-1]:parent=parent['files'].setdefault(part,{'files':{}})
            parent['files'][parts[-1]]={'size':len(data),'offset':str(len(payload)),'integrity':patch.integrity_of(data)}
            payload+=data
        self.header['files']['native.node']={'size':4,'unpacked':True,'integrity':patch.integrity_of(b'test')}
        self.header['files']['alias']={'link':'empty.txt'}
        self.source.write_bytes(patch.serialize_header(self.header)+payload)
        self.allowed=patch.SUPPORTED_ORIGINAL_HASHES.copy()
        patch.SUPPORTED_ORIGINAL_HASHES.add(patch.file_hash(self.source))
        self.out=self.root/'output';self.out.mkdir()
    def tearDown(self):
        patch.SUPPORTED_ORIGINAL_HASHES=self.allowed;self.temp.cleanup()
    def make(self):
        with contextlib.redirect_stdout(io.StringIO()):patch.make_patch(self.source,self.image,self.out)
        return self.out/'app.asar.custom-bg'
    def test_complete_patch(self):
        result=self.make();header,start=patch.read_archive(result);mapping=patch.entries(header)
        self.assertEqual(len(mapping),len(patch.entries(self.header))+1)
        self.assertIn(patch.STYLE.encode(),patch.packed_bytes(result,start,mapping[patch.INDEX_PATH]))
        self.assertEqual(mapping['native.node'],self.header['files']['native.node'])
        self.assertEqual(mapping['alias'],self.header['files']['alias'])
        info=json.loads((self.out/'补丁信息.json').read_text(encoding='utf-8'))
        self.assertEqual(info['schemaVersion'],1);self.assertEqual(info['originalHash'],patch.file_hash(self.source))
        self.assertEqual(info['patchedHash'],patch.file_hash(result));self.assertNotIn('asarPath',info)
    def test_unknown_version_refused(self):
        patch.SUPPORTED_ORIGINAL_HASHES.clear()
        with self.assertRaisesRegex(ValueError,'尚未验证'):self.make()
        self.assertEqual(list(self.out.iterdir()),[])
    def test_existing_output_preserved(self):
        existing=self.out/'app.asar.custom-bg';existing.write_bytes(b'keep')
        with self.assertRaises(ValueError):self.make()
        self.assertEqual(existing.read_bytes(),b'keep')
    def test_invalid_image_does_not_leave_output(self):
        self.image.write_bytes(b'not an image')
        with self.assertRaises(Exception):self.make()
        self.assertEqual(list(self.out.iterdir()),[])
    def test_tiny_image_refused(self):
        Image.new('RGB',(10,10)).save(self.image)
        with self.assertRaisesRegex(ValueError,'太小'):self.make()
    def test_verification_failure_cleans_output(self):
        old=patch.verify_entries
        def fail(*args):raise ValueError('injected verification failure')
        patch.verify_entries=fail
        try:
            with self.assertRaises(ValueError):self.make()
        finally:patch.verify_entries=old
        self.assertEqual(list(self.out.iterdir()),[])
    def test_source_change_refused(self):
        old=patch.verify_entries
        def mutate(*args):
            result=old(*args)
            with self.source.open('ab') as f:f.write(b'changed')
            return result
        patch.verify_entries=mutate
        try:
            with self.assertRaisesRegex(ValueError,'原程序被修改'):self.make()
        finally:patch.verify_entries=old
        self.assertEqual(list(self.out.iterdir()),[])
    def test_directory_lock(self):
        lock=self.out/'.制作中.lock';lock.write_text('other process')
        with self.assertRaises(FileExistsError):self.make()
        self.assertEqual(lock.read_text(),'other process')
    def test_wallpaper_roundtrip(self):
        patched=self.make();new_image=self.root/'second.png';Image.new('RGB',(150,80),'blue').save(new_image)
        changed=self.root/'changed.asar'
        with contextlib.redirect_stdout(io.StringIO()):swap.replace_wallpaper(patched,changed,new_image)
        h,s=patch.read_archive(patched);h2,s2=patch.read_archive(changed);a,b=patch.entries(h),patch.entries(h2)
        for name in a:
            if 'offset' in a[name] and name!=patch.IMAGE_PATH:
                self.assertEqual(patch.packed_bytes(patched,s,a[name]),patch.packed_bytes(changed,s2,b[name]))
        data=patch.packed_bytes(changed,s2,b[patch.IMAGE_PATH]);self.assertEqual(Image.open(io.BytesIO(data)).size,(150,80))
        self.assertEqual(hashlib.sha256(data).hexdigest(),b[patch.IMAGE_PATH]['integrity']['hash'])
    def test_swap_unpatched_refused(self):
        with self.assertRaisesRegex(ValueError,'没有安装'):swap.replace_wallpaper(self.source,self.root/'new.asar',self.image)
    def test_swap_existing_output_preserved(self):
        result=self.make();destination=self.root/'existing';destination.write_bytes(b'keep')
        with self.assertRaises(ValueError):swap.replace_wallpaper(result,destination,self.image)
        self.assertEqual(destination.read_bytes(),b'keep')
    def test_swap_source_cannot_be_destination(self):
        result=self.make()
        with self.assertRaises(ValueError):swap.replace_wallpaper(result,result,self.image)
    def test_header_rejects_truncated_or_invalid(self):
        for raw in [b'',b'0'*16,struct.pack('<4I',4,4,0,0),struct.pack('<4I',4,12,8,400),struct.pack('<4I',4,16,12,2)+b'{}']:
            bad=self.root/'bad';bad.write_bytes(raw)
            with self.assertRaises(Exception):patch.read_archive(bad)
    def test_unsafe_paths_refused(self):
        for name in ['..','a/b','a\\b']:
            with self.assertRaises(ValueError):patch.entries({'files':{name:{'size':0,'offset':'0'}}})
    def test_out_of_range_entry_refused(self):
        with self.assertRaises(ValueError):patch.packed_bytes(self.source,0,{'size':999999,'offset':'0'})
    def test_empty_file_integrity(self):
        self.assertEqual(patch.integrity_of(b'')['blocks'],[hashlib.sha256(b'').hexdigest()])
if __name__=='__main__':unittest.main(verbosity=2)
