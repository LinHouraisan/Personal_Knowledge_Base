import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser


def demo_ready(url):
    try:
        with urlopen(url + "v1/capabilities", timeout=1) as response:
            capabilities = json.load(response)
        if capabilities.get("demo") is not True:
            return False
        with urlopen(url + "v1/ai/connection", timeout=1) as response:
            if json.load(response).get("available") is not True:
                return False
        with urlopen(url + "v1/workspace", timeout=1) as response:
            return isinstance(json.load(response).get("goals"), list)
    except (OSError, URLError, ValueError):
        return False


def ensure_demo(port=8011):
    url = f"http://127.0.0.1:{port}/"
    if demo_ready(url):
        return url, None
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise RuntimeError(f"端口 {port} 正被其他程序或旧版演示使用。可使用 --port 8012 启动。") from None
    root = Path(__file__).resolve().parents[1]
    log_dir = root / "data"
    log_dir.mkdir(exist_ok=True)
    with (log_dir / "demo.log").open("ab") as log:
        process = subprocess.Popen([sys.executable, "-B", "-m", "app.demo", "--ai", "--port", str(port)],
                                   cwd=root, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError("演示启动失败，请查看 data/demo.log。")
            if demo_ready(url):
                return url, process
            time.sleep(0.25)
        raise RuntimeError("演示暂未就绪，请查看 data/demo.log 后重试。")
    except BaseException:
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/pid", str(process.pid), "/t", "/f"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                process.terminate()
        process.wait(timeout=5)
        raise


def main():
    parser = argparse.ArgumentParser(description="打开个人知识库公开演示")
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        url, _ = ensure_demo(args.port)
    except RuntimeError as error:
        print(str(error))
        return 1
    if not args.no_browser:
        webbrowser.open(url)
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
