"""Local web GUI for vphone-linux.

A zero-dependency control panel (Python stdlib http.server only) so the whole
flow — configure, build, fetch, restore, boot, companion — is point-and-click
instead of memorising command lines. It runs the very same `vphone_linux` CLI
under the hood and streams its output into a console pane, so the GUI never
diverges from the CLI behaviour.

Design follows the project system: dark neutral background, status accents,
monospace, flat 1px borders.

Launch with `vphone-linux gui [workspace]`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .backends import BACKENDS
from .config import Config

PKG_PARENT = str(Path(__file__).resolve().parent.parent)


# ─── job manager: run a CLI command, accumulate output ───────────────
class Job:
    def __init__(self, argv: list[str]):
        self.argv = argv
        self.lines: list[str] = []
        self.done = False
        self.returncode: int | None = None
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = PKG_PARENT + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONUNBUFFERED"] = "1"
        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-m", "vphone_linux", *self.argv],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=env,
            )
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                with self._lock:
                    self.lines.append(line.rstrip("\n"))
            self._proc.wait()
            with self._lock:
                self.returncode = self._proc.returncode
                self.done = True
        except Exception as exc:  # surface failures into the console
            with self._lock:
                self.lines.append(f"[gui] job error: {exc}")
                self.returncode = -1
                self.done = True

    def snapshot(self, start: int) -> dict:
        with self._lock:
            return {
                "lines": self.lines[start:],
                "total": len(self.lines),
                "done": self.done,
                "returncode": self.returncode,
            }

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[int, Job] = {}
        self._next = 1
        self._lock = threading.Lock()

    def launch(self, argv: list[str]) -> int:
        with self._lock:
            jid = self._next
            self._next += 1
            job = Job(argv)
            self._jobs[jid] = job
        job.start()
        return jid

    def get(self, jid: int) -> Job | None:
        return self._jobs.get(jid)


JOBS = JobManager()


# ─── argument mapping (GUI action → CLI argv) ────────────────────────
def _cfg_flags(p: dict) -> list[str]:
    """Build the init flags from posted form values."""
    return [
        "--backend", str(p.get("backend", "chefkiss")),
        "--device", str(p.get("device", "t8030")),
        "--cpus", str(p.get("cpus", 4)),
        "--memory-mb", str(p.get("memory_mb", 4096)),
        "--net", str(p.get("network", "usb-bridge")),
        "--ssh-port", str(p.get("ssh_host_port", 2222)),
        "--display", str(p.get("display", "auto")),
        "--gl", str(p.get("gl", "on")),
        "--vnc", str(p.get("vnc_display", 0)),
        "--tcg-thread", str(p.get("tcg_thread", "single")),
        "--tb-size-mb", str(p.get("tb_size_mb", 256)),
    ]


def build_argv(action: str, ws: str, params: dict) -> list[str]:
    p = params or {}
    if action == "init":
        return ["init", ws, *_cfg_flags(p)]
    if action == "doctor":
        return ["doctor", ws]
    if action == "build":
        return ["build", ws]
    if action == "fetch":
        return ["fetch", ws, str(p.get("ipsw", ""))]
    if action == "prepare":
        return ["prepare", ws, "--main-gb", str(p.get("main_gb", 16))]
    if action == "plan":
        a = ["plan", ws]
        if p.get("restore"):
            a.append("--restore")
        return a
    if action == "restore":
        return ["restore", ws]
    if action == "boot":
        return ["boot", ws]
    if action == "companion":
        return ["companion", ws]
    if action == "ssh":
        return ["ssh", ws]
    raise ValueError(f"unknown action '{action}'")


# ─── HTTP handler ────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "vphone-linux-gui"

    def log_message(self, *args):  # silence default logging
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode())
        except Exception:
            return {}

    # ── GET ──
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._send(200, INDEX_HTML.encode(), "text/html; charset=utf-8")
            return
        if u.path == "/api/state":
            q = parse_qs(u.query)
            ws = (q.get("ws") or [""])[0]
            self._json(200, self._state(ws))
            return
        if u.path == "/api/job":
            q = parse_qs(u.query)
            jid = int((q.get("id") or ["0"])[0])
            start = int((q.get("from") or ["0"])[0])
            job = JOBS.get(jid)
            if not job:
                self._json(404, {"error": "no such job"})
                return
            self._json(200, job.snapshot(start))
            return
        self._send(404, b"not found", "text/plain")

    # ── POST ──
    def do_POST(self):
        u = urlparse(self.path)
        body = self._read_body()
        if u.path == "/api/run":
            ws = body.get("ws", "")
            action = body.get("action", "")
            if not ws:
                self._json(400, {"error": "workspace path required"})
                return
            try:
                argv = build_argv(action, ws, body.get("params", {}))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            jid = JOBS.launch(argv)
            self._json(200, {"job": jid, "argv": argv})
            return
        if u.path == "/api/stop":
            job = JOBS.get(int(body.get("job", 0)))
            if job:
                job.stop()
            self._json(200, {"ok": True})
            return
        self._send(404, b"not found", "text/plain")

    def _state(self, ws: str) -> dict:
        out = {"backends": sorted({b.key for b in BACKENDS.values()}), "workspace": ws}
        try:
            cfg = Config.load(Path(ws)) if ws else Config()
            out["exists"] = bool(ws) and (Path(ws) / "vphone-linux.toml").exists()
        except FileNotFoundError:
            cfg = Config()
            out["exists"] = False
        out["config"] = asdict(cfg)
        return out


def serve(workspace: str, host: str = "127.0.0.1", port: int = 8723, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"vphone-linux GUI → {url}", file=sys.stderr)
    print("  (Ctrl-C to stop)", file=sys.stderr)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nGUI stopped.", file=sys.stderr)
        httpd.shutdown()


def _entry() -> None:
    """Console-script entry: `vphone-linux-gui [workspace]`."""
    ws = sys.argv[1] if len(sys.argv) > 1 else ""
    serve(ws)


# ─── single-page UI ──────────────────────────────────────────────────
INDEX_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>vphone-linux</title>
<style>
:root{--bg:#1a1a1a;--panel:#222;--border:#333;--fg:#ddd;--dim:#888;
--green:#4caf50;--amber:#ffb300;--red:#ef5350;--blue:#42a5f5;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font-family:"SF Mono",Menlo,Consolas,monospace;font-size:13px;line-height:1.5}
header{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;
align-items:center;gap:12px}
header h1{font-size:15px;margin:0;font-weight:600}
header .tag{color:var(--dim);font-size:12px}
.wrap{display:grid;grid-template-columns:340px 1fr;gap:16px;padding:16px;
height:calc(100vh - 50px)}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:4px;
padding:12px;overflow:auto}
.panel h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;
color:var(--dim);margin:0 0 10px}
label{display:block;margin:8px 0 2px;color:var(--dim);font-size:11px}
input,select{width:100%;background:#1a1a1a;border:1px solid var(--border);
color:var(--fg);padding:6px 8px;border-radius:3px;font-family:inherit;font-size:12px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.btns{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
button{background:#2a2a2a;border:1px solid var(--border);color:var(--fg);
padding:6px 10px;border-radius:3px;cursor:pointer;font-family:inherit;font-size:12px}
button:hover{border-color:#555}
button.primary{border-color:var(--green);color:var(--green)}
button.run{border-color:var(--blue);color:var(--blue)}
button.danger{border-color:var(--red);color:var(--red)}
#console{background:#111;border:1px solid var(--border);border-radius:4px;
padding:10px;height:100%;overflow:auto;white-space:pre-wrap;font-size:12px}
.con-info{color:var(--blue)}.con-ok{color:var(--green)}
.con-warn{color:var(--amber)}.con-err{color:var(--red)}.con-dim{color:var(--dim)}
.status{margin-left:auto;font-size:12px}
.note{color:var(--dim);font-size:11px;margin-top:6px;border-top:1px solid var(--border);padding-top:8px}
.hint{color:var(--amber);font-size:11px;margin-top:4px}
</style></head><body>
<header>
  <h1>vphone-linux</h1>
  <span class="tag">iOS-on-QEMU control panel</span>
  <span class="status" id="status">idle</span>
</header>
<div class="wrap">
  <div class="panel">
    <h2>Workspace</h2>
    <label>Workspace path</label>
    <input id="ws" placeholder="/path/to/ws" />
    <div class="btns"><button onclick="loadState()">Load</button></div>

    <h2 style="margin-top:16px">Configuration</h2>
    <label>Backend (QEMU fork)</label>
    <select id="backend"><option>chefkiss</option><option>trung</option></select>
    <div class="row">
      <div><label>CPUs</label><input id="cpus" type="number" value="4"></div>
      <div><label>Memory (MiB)</label><input id="memory_mb" type="number" value="4096"></div>
    </div>
    <label>Network</label>
    <select id="network"><option>usb-bridge</option><option>user</option><option>off</option></select>
    <div class="row">
      <div><label>SSH host port</label><input id="ssh_host_port" type="number" value="2222"></div>
      <div><label>VNC display (0=off)</label><input id="vnc_display" type="number" value="0"></div>
    </div>
    <div class="row">
      <div><label>Display</label>
        <select id="display"><option>auto</option><option>gtk</option><option>sdl</option>
        <option>egl-headless</option><option>vnc</option><option>none</option></select></div>
      <div><label>Host GPU GL</label><select id="gl"><option>on</option><option>off</option></select></div>
    </div>
    <div class="row">
      <div><label>TCG thread</label><select id="tcg_thread"><option>single</option><option>multi</option></select></div>
      <div><label>TB cache (MiB)</label><input id="tb_size_mb" type="number" value="256"></div>
    </div>
    <div class="hint" id="archhint"></div>
    <div class="btns"><button class="primary" onclick="run('init')">Save config</button></div>

    <h2 style="margin-top:16px">Firmware</h2>
    <label>IPSW path (for Fetch)</label>
    <input id="ipsw" placeholder="/path/iPhone12,1_14.x.ipsw" />
    <div class="row">
      <div><label>Main disk (GB)</label><input id="main_gb" type="number" value="16"></div>
    </div>

    <div class="note">KVM never applies to t8030 — always TCG. On x86_64 try
    TCG&nbsp;multi + a larger TB cache for smoother SMP. iOS rendering stays
    software; gl=on only accelerates presentation.</div>
  </div>

  <div style="display:flex;flex-direction:column;gap:10px;min-height:0">
    <div class="panel" style="flex:0 0 auto">
      <h2>Actions</h2>
      <div class="btns">
        <button onclick="run('doctor')">Doctor</button>
        <button class="run" onclick="run('build')">Build QEMU</button>
        <button class="run" onclick="run('fetch')">Fetch IPSW</button>
        <button onclick="run('prepare')">Prepare disks</button>
        <button onclick="run('plan')">Show plan</button>
        <button class="run" onclick="run('companion')">Companion VM</button>
        <button class="primary" onclick="run('restore')">Restore</button>
        <button class="primary" onclick="run('boot')">Boot</button>
        <button onclick="run('ssh')">SSH info</button>
        <button class="danger" onclick="stopJob()">Stop</button>
        <button onclick="clearCon()">Clear</button>
      </div>
    </div>
    <pre id="console" class="panel"></pre>
  </div>
</div>
<script>
let curJob=null, fromLine=0, poll=null;
const $=id=>document.getElementById(id);
function setStatus(s,cls){const e=$('status');e.textContent=s;e.className='status '+(cls||'')}
function classify(l){if(/^\[\+\]/.test(l))return'con-ok';if(/^\[!\]/.test(l))return'con-warn';
if(/^\[x\]/.test(l))return'con-err';if(/^\[\*\]/.test(l))return'con-info';
if(/^\s*\$/.test(l)||/^══/.test(l))return'con-dim';return''}
function append(lines){const c=$('console');lines.forEach(l=>{const s=document.createElement('span');
s.className=classify(l);s.textContent=l+"\n";c.appendChild(s)});c.scrollTop=c.scrollHeight}
function clearCon(){$('console').innerHTML=''}
function params(){return{backend:$('backend').value,device:'t8030',cpus:+$('cpus').value,
memory_mb:+$('memory_mb').value,network:$('network').value,ssh_host_port:+$('ssh_host_port').value,
display:$('display').value,gl:$('gl').value,vnc_display:+$('vnc_display').value,
tcg_thread:$('tcg_thread').value,tb_size_mb:+$('tb_size_mb').value,
ipsw:$('ipsw').value,main_gb:+$('main_gb').value,restore:false}}
async function run(action){const ws=$('ws').value.trim();if(!ws){alert('Set a workspace path first');return}
const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({ws,action,params:params()})});const j=await r.json();
if(j.error){append(['[x] '+j.error]);return}
append(['','══ '+action+'  ($ vphone-linux '+j.argv.join(' ')+')']);
curJob=j.job;fromLine=0;setStatus(action+' running…','con-info');
if(poll)clearInterval(poll);poll=setInterval(pollJob,500)}
async function pollJob(){if(curJob==null)return;
const r=await fetch('/api/job?id='+curJob+'&from='+fromLine);const j=await r.json();
if(j.lines&&j.lines.length){append(j.lines);fromLine=j.total}
if(j.done){clearInterval(poll);poll=null;
setStatus('done (exit '+j.returncode+')',j.returncode===0?'con-ok':'con-err');
if(['init','fetch','build'].length)loadState();curJob=null}}
async function stopJob(){if(curJob!=null){await fetch('/api/stop',{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify({job:curJob})});
append(['[!] stop requested'])}}
async function loadState(){const ws=$('ws').value.trim();
const r=await fetch('/api/state?ws='+encodeURIComponent(ws));const j=await r.json();
const c=j.config||{};for(const k of ['backend','cpus','memory_mb','network','ssh_host_port',
'display','gl','vnc_display','tcg_thread','tb_size_mb'])if($(k)&&c[k]!==undefined)$(k).value=c[k];
setStatus(j.exists?'config loaded':'new workspace',j.exists?'con-ok':'con-warn')}
$('archhint').textContent = navigator.platform.includes('64')?
  'Host appears 64-bit. On x86_64 this is TCG (no KVM); multi + big TB cache = smoother.':'';
</script></body></html>"""
