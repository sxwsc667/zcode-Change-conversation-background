"""在明确提供的真实程序副本上执行完整流程，不操作真实安装。"""
import argparse, hashlib, json, subprocess, sys, os
from pathlib import Path
TOOLS=Path(__file__).resolve().parents[1]/'tools'/'通用版'
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work',required=True);args=parser.parse_args()
    base=Path(args.work).resolve();resources=base/'智码测试副本'/'resources';patchdir=base/'补丁输出'
    # 防止把正式目录误传进测试。
    assert base in resources.parents and resources.parent.name=='智码测试副本'
    target=resources/'app.asar';info=json.loads((patchdir/'补丁信息.json').read_text(encoding='utf-8'))
    assert sha(target)==info['originalHash'],'测试必须从原版副本开始'
    before_real=sha(Path(r'E:\ZCode\resources\app.asar')) if Path(r'E:\ZCode\resources\app.asar').is_file() else None
    def call(name,*extra,ok=True):
        command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(TOOLS/(name+'.ps1')),'-ResourcesDir',str(resources),*map(str,extra)]
        environment=os.environ.copy()
        done=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=environment)
        if (done.returncode==0)!=ok:raise AssertionError(done.stdout.decode('utf-8',errors='replace'))
    results=[]
    def passed(name):results.append(name);print('通过：'+name,flush=True)
    call('安装背景补丁','-PatchDir',patchdir);assert sha(target)==info['patchedHash'];passed('首次安装')
    call('安装背景补丁','-PatchDir',patchdir);assert sha(target)==info['patchedHash'];passed('重复安装不改动')
    from PIL import Image
    image=base/'新壁纸.png';Image.new('RGB',(320,180),'#123ABC').save(image)
    call('更换壁纸','-ImagePath',image,'-Python',sys.executable)
    changed=sha(target);assert changed!=info['patchedHash'];passed('更换壁纸并更新安装记录')
    call('安装背景补丁','-PatchDir',patchdir);assert sha(target)==changed;passed('换图后重复安装不覆盖新壁纸')
    image.write_bytes(b'bad image')
    call('更换壁纸','-ImagePath',image,'-Python',sys.executable,ok=False);assert sha(target)==changed;passed('坏图片不破坏程序')
    call('恢复原版');assert sha(target)==info['originalHash'];passed('换图后恢复原版')
    call('恢复原版');assert sha(target)==info['originalHash'];passed('重复恢复不改动')
    call('安装背景补丁','-PatchDir',patchdir);assert sha(target)==info['patchedHash'];passed('恢复后再次安装')
    # 模拟升级：只改变测试副本的尾部，三个工具都必须拒绝，不能降级。
    with target.open('ab') as f:f.write(b'upgraded-version-test')
    upgraded=sha(target)
    for name,extra in [('恢复原版',()),('安装背景补丁',('-PatchDir',patchdir)),('更换壁纸',('-ImagePath',image,'-Python',sys.executable))]:
        call(name,*extra,ok=False);assert sha(target)==upgraded
    passed('升级后安装、换图、恢复全部拒绝覆盖')
    with target.open('r+b') as f:f.truncate(target.stat().st_size-len(b'upgraded-version-test'))
    assert sha(target)==info['patchedHash']
    restore=resources/'app.asar.custom-bg-restore'
    with restore.open('ab') as f:f.write(b'bad')
    call('恢复原版',ok=False);assert sha(target)==info['patchedHash'];passed('损坏恢复点拒绝覆盖')
    with restore.open('r+b') as f:f.truncate(restore.stat().st_size-3)
    state=resources/'app.asar.custom-bg-state.json';saved=state.read_bytes();state.write_text('{}')
    call('恢复原版',ok=False);assert sha(target)==info['patchedHash'];state.write_bytes(saved);passed('损坏安装记录拒绝覆盖')
    patchfile=patchdir/'app.asar.custom-bg'
    with patchfile.open('ab') as f:f.write(b'bad')
    call('安装背景补丁','-PatchDir',patchdir,ok=False);assert sha(target)==info['patchedHash'];passed('损坏补丁拒绝覆盖')
    with patchfile.open('r+b') as f:f.truncate(patchfile.stat().st_size-3)
    call('恢复原版');assert sha(target)==info['originalHash'];passed('异常拒绝后仍可正常恢复')
    if before_real:
        assert sha(Path(r'E:\ZCode\resources\app.asar'))==before_real;passed('正式安装前后完全一致')
    (base/'完整流程结果.json').write_text(json.dumps({'passed':results,'count':len(results)},ensure_ascii=False,indent=2),encoding='utf-8')
    print(str(len(results))+' 项完整流程检查全部通过。')
if __name__=='__main__':main()


