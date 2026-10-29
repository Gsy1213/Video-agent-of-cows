import hashlib,json,os,re,shutil,subprocess
from pathlib import Path
import imageio_ffmpeg
from .config import DATA
from .db import uid

FFMPEG=imageio_ffmpeg.get_ffmpeg_exe()
def probe(path):
    # Bundled ffmpeg probes actual media; no filename/header trust.
    p=subprocess.run([FFMPEG,'-i',str(path),'-f','null','-t','0','-'],capture_output=True,text=True,timeout=15)
    text=p.stderr
    d=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',text)
    stream=next((x for x in text.splitlines() if 'Video:' in x),'')
    size=re.search(r' (\d{2,5})x(\d{2,5})',stream);fps=re.search(r'([\d.]+) fps',stream)
    if not d or not size or not fps:raise ValueError('无法读取视频媒体信息')
    duration=int(d[1])*3600+int(d[2])*60+float(d[3])
    if duration<=0:raise ValueError('视频时长无效')
    return dict(duration_s=duration,width=int(size[1]),height=int(size[2]),fps=float(fps[1]),sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

def demo_media():
    source=Path(os.getenv('DEMO_VIDEO_PATH','/data2/geshuyu/5.mp4')).expanduser().resolve()
    if not source.is_file():raise ValueError('演示视频不存在，请配置 DEMO_VIDEO_PATH')
    meta=probe(source)
    path=DATA/'videos'/f'{uid()}.mp4'
    shutil.copyfile(source,path)
    return path,meta

def synthetic_demo_media():
    """Explicit test fixture only; never used as the product demo fallback."""
    path=DATA/'videos'/f'{uid()}.mp4'
    from PIL import Image,ImageDraw,ImageFont
    mark=DATA/'jobs'/f'{uid()}.png'
    image=Image.new('RGBA',(640,360),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.rectangle((12,12,628,65),fill=(0,0,0,210))
    draw.text((25,27),'DEMO - SYNTHETIC TEST VIDEO',fill='white',font=ImageFont.load_default(size=25));image.save(mark)
    try:
        subprocess.run([FFMPEG,'-y','-f','lavfi','-i','testsrc2=size=640x360:rate=10','-i',str(mark),'-filter_complex','overlay=0:0','-t','120','-c:v','libx264','-preset','ultrafast','-crf','32','-pix_fmt','yuv420p','-movflags','+faststart',str(path)],capture_output=True,check=True,timeout=60)
    finally:mark.unlink(missing_ok=True)
    return path,probe(path)
