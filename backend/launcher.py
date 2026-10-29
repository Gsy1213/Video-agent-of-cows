import argparse,os,signal,subprocess,sys,time
import httpx
from backend.app.config import ROOT,DATA

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dev',action='store_true');parser.add_argument('--port',type=int,default=8000);args=parser.parse_args()
    children=[]
    def stop(*_):
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
    try:
        if not args.dev and not (ROOT/'frontend/dist/index.html').exists():subprocess.run(['npm','run','build'],cwd=ROOT/'frontend',check=True)
        children.append(subprocess.Popen([sys.executable,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(args.port)],cwd=ROOT))
        base=f'http://127.0.0.1:{args.port}'
        for _ in range(100):
            if children[0].poll() is not None:raise RuntimeError('API 启动失败，请检查端口与日志')
            try:
                if httpx.get(base+'/api/health',timeout=1).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.2)
        else:raise RuntimeError('API 启动超时')
        children.append(subprocess.Popen([sys.executable,'-m','backend.worker'],cwd=ROOT))
        from backend.seed import seed
        marker=DATA/'.seed-complete'
        if not marker.exists():
            docs=seed(base,video=False)
            if docs and all(d['status']=='ready' for d in docs):marker.write_text('initial API ingestion completed\n')
        if args.dev:
            children.append(subprocess.Popen(['npm','run','dev'],cwd=ROOT/'frontend'));print('前端：http://127.0.0.1:5173',flush=True)
        else:print(f'牧知演示：{base}/videos',flush=True)
        while all(p.poll() is None for p in children):time.sleep(1)
        raise RuntimeError('服务进程意外退出，请检查日志')
    except KeyboardInterrupt:pass
    finally:stop()
if __name__=='__main__':main()
