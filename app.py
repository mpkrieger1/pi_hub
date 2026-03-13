import os
import re
import json
import time
import shutil
import subprocess
from pathlib import Path

from flask import Flask, render_template, request, jsonify

APP_NAME = "Pi Hub"
HANDBRAKE_BIN = "HandBrakeCLI"
DVD_DEVICE = "/dev/sr0"

DATA_DIR = Path("/mnt/docker/apps/hub")
LOG_DIR = DATA_DIR / "logs"
JOBS_DIR = DATA_DIR / "jobs"
BASEBALL_REPO = Path("/home/mpkrieger1/apps/baseball_sim")
MYFLOW_REPO = Path("/home/mpkrieger1/apps/my_flow/repo")
MLB_DB_PATH = "/mnt/ssd/data/baseball_sim/mlb.sqlite"
HUB_PUBLIC_URL = "https://hub.thedataball.com"
BASEBALL_PUBLIC_URL = "https://thedataball.com"
MYFLOW_PUBLIC_URL = "https://reports.k-analytics.co"

ALLOWED_OUTPUT_DIRS = {
    "movies": "/mnt/ssd/Movies",
    "videos": "/mnt/ssd/Videos",
    "rips": "/mnt/ssd/rips",
}

PRESETS = [
    "Fast 1080p30",
    "Fast 720p30",
    "Very Fast 1080p30",
    "HQ 1080p30 Surround",
]

DEFAULTS = {
    "output_key": "movies",
    "preset": "Fast 1080p30",
    "title": "1",
}


def ensure_dirs():
    for p in (DATA_DIR, LOG_DIR, JOBS_DIR):
        p.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^\w\s\-\.\(\)]", "_", name)
    name = name.replace("/", "_").replace("\\", "_")
    if not name:
        name = f"rip_{int(time.time())}"
    if not name.lower().endswith((".m4v", ".mp4", ".mkv")):
        name += ".m4v"
    return name


def read_temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        return None


def read_uptime():
    try:
        with open("/proc/uptime", "r") as f:
            seconds = int(float(f.read().split()[0]))
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        return f"{days}d {hours}h {minutes}m"
    except Exception:
        return "unknown"


def disk_usage(path):
    try:
        total, used, free = shutil.disk_usage(path)
        return {
            "total_gb": round(total / (1024**3), 1),
            "used_gb": round(used / (1024**3), 1),
            "free_gb": round(free / (1024**3), 1),
        }
    except Exception:
        return None


def job_file():
    return JOBS_DIR / "current.json"


def scan_file():
    return JOBS_DIR / "scan.json"

def deploy_file():
    return JOBS_DIR / "deploy.json"

def myflow_deploy_file():
    return JOBS_DIR / "myflow_deploy.json"


def load_job():
    if job_file().exists():
        try:
            return json.loads(job_file().read_text())
        except Exception:
            return {"status": "idle"}
    return {"status": "idle"}


def save_job(job):
    job_file().write_text(json.dumps(job, indent=2))


def save_scan(data):
    scan_file().write_text(json.dumps(data, indent=2))

def save_deploy(job):
    deploy_file().write_text(json.dumps(job, indent=2))


def load_scan():
    if scan_file().exists():
        try:
            return json.loads(scan_file().read_text())
        except Exception:
            return {"titles": [], "raw": ""}
    return {"titles": [], "raw": ""}


def load_deploy():
    if deploy_file().exists():
        try:
            return json.loads(deploy_file().read_text())
        except Exception:
            return {"status": "idle"}
    return {"status": "idle"}


def save_myflow_deploy(job):
    myflow_deploy_file().write_text(json.dumps(job, indent=2))


def load_myflow_deploy():
    if myflow_deploy_file().exists():
        try:
            return json.loads(myflow_deploy_file().read_text())
        except Exception:
            return {"status": "idle"}
    return {"status": "idle"}


def myflow_service_status():
    """Get MyFlow systemd service status and last git pull info."""
    info = {"active": False, "status": "unknown", "last_pull": None, "commit": None}
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "myflow"],
            capture_output=True, text=True, timeout=5,
        )
        status = result.stdout.strip()
        info["active"] = status == "active"
        info["status"] = status
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H|%s|%ar"],
            capture_output=True, text=True, timeout=5,
            cwd=str(MYFLOW_REPO),
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|", 2)
            if len(parts) == 3:
                info["commit"] = parts[0][:8]
                info["message"] = parts[1]
                info["last_pull"] = parts[2]
    except Exception:
        pass
    return info


def tail_file(path, lines=200):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            buf = bytearray()
            block = 1024
            while len(buf.splitlines()) <= lines and end > 0:
                read_size = block if end - block > 0 else end
                end -= read_size
                f.seek(end)
                buf = f.read(read_size) + buf
            return b"\n".join(buf.splitlines()[-lines:]).decode(errors="replace")
    except Exception:
        return ""


app = Flask(__name__)
ensure_dirs()


@app.route("/")
def index():
    return render_template(
        "index.html",
        app_name=APP_NAME,
        temp_c=read_temp_c(),
        uptime=read_uptime(),
        disk_ssd=disk_usage("/mnt/ssd"),
        disk_docker=disk_usage("/mnt/docker"),
        allowed_outputs=ALLOWED_OUTPUT_DIRS,
        presets=PRESETS,
        defaults=DEFAULTS,
        hub_url=HUB_PUBLIC_URL,
        baseball_url=BASEBALL_PUBLIC_URL,
        myflow_url=MYFLOW_PUBLIC_URL,
        myflow=myflow_service_status(),
    )


@app.route("/start", methods=["POST"])
def start_job():
    job = load_job()
    if job.get("status") == "running":
        return jsonify({"ok": False, "error": "A job is already running."}), 409

    preset = request.form.get("preset", DEFAULTS["preset"]).strip()
    subtitle_track = request.form.get("subtitle_track", "none").strip()
    subtitle_burn = request.form.get("subtitle_burn") == "on"
    output_key = request.form.get("output_key", DEFAULTS["output_key"]).strip()
    filename = sanitize_filename(request.form.get("filename", "movie.m4v"))
    titles_raw = request.form.get("titles_json", "").strip()
    try:
        titles_payload = json.loads(titles_raw) if titles_raw else []
    except json.JSONDecodeError:
        titles_payload = []
    titles = []
    for item in titles_payload:
        number = str(item.get("number", "")).strip()
        if not number.isdigit():
            continue
        titles.append(
            {
                "number": number,
                "filename": sanitize_filename(str(item.get("filename", "")).strip()) if item.get("filename") else "",
            }
        )

    if output_key not in ALLOWED_OUTPUT_DIRS:
        return jsonify({"ok": False, "error": "Invalid output folder."}), 400
    if preset not in PRESETS:
        return jsonify({"ok": False, "error": "Invalid preset."}), 400
    if subtitle_track != "none" and not subtitle_track.isdigit():
        return jsonify({"ok": False, "error": "Invalid subtitle selection."}), 400
    if not titles:
        return jsonify({"ok": False, "error": "Select at least one title to rip."}), 400

    output_dir = ALLOWED_OUTPUT_DIRS[output_key]
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    base_name = Path(filename).stem
    extension = Path(filename).suffix or ".m4v"

    job = {
        "status": "queued",
        "pid": None,
        "started_at": int(time.time()),
        "preset": preset,
        "subtitle_track": subtitle_track,
        "subtitle_burn": subtitle_burn,
        "output_dir": output_dir,
        "base_name": base_name,
        "extension": extension,
        "multi": len(titles) > 1,
        "pending_titles": titles,
        "current_title": None,
        "output_path": None,
        "log_path": None,
        "cmd": None,
    }
    job = start_next_title(job)
    save_job(job)

    return jsonify({"ok": True, "job": job})


@app.route("/status")
def status():
    job = load_job()
    if job.get("status") == "running":
        pid = job.get("pid")
        if pid and os.path.exists(f"/proc/{pid}"):
            job["running"] = True
        else:
            job["running"] = False
            if job.get("pending_titles"):
                job = start_next_title(job)
            else:
                job["status"] = "finished"
                save_job(job)
    log_text = tail_file(job.get("log_path", "")) if job.get("log_path") else ""
    return jsonify({"job": job, "log_tail": log_text})


@app.route("/stop", methods=["POST"])
def stop():
    job = load_job()
    pid = job.get("pid")
    if pid and os.path.exists(f"/proc/{pid}"):
        try:
            os.kill(pid, 15)
        except Exception:
            pass
    job["status"] = "stopped"
    job["pending_titles"] = []
    save_job(job)
    return jsonify({"ok": True})


@app.route("/deploy/start", methods=["POST"])
def deploy_start():
    job = load_deploy()
    if job.get("status") == "running":
        return jsonify({"ok": False, "error": "Deploy already running."}), 409

    log_path = str(LOG_DIR / f"deploy_{int(time.time())}.log")
    cmd = (
        "mkdir -p /mnt/ssd/data/baseball_sim && "
        "git fetch --all && "
        "git reset --hard origin/main && "
        "git clean -fd && "
        "npm install && "
        f"export MLB_DB_PATH={MLB_DB_PATH} && "
        "npm run build && "
        "sudo /bin/systemctl restart baseball_sim"
    )
    env = os.environ.copy()
    env["MLB_DB_PATH"] = MLB_DB_PATH

    with open(log_path, "a") as log:
        proc = subprocess.Popen(
            ["bash", "-lc", cmd],
            cwd=str(BASEBALL_REPO),
            stdout=log,
            stderr=log,
            env=env,
        )

    job = {
        "status": "running",
        "pid": proc.pid,
        "started_at": int(time.time()),
        "log_path": log_path,
        "cmd": cmd,
    }
    save_deploy(job)
    return jsonify({"ok": True, "job": job})


@app.route("/deploy/status")
def deploy_status():
    job = load_deploy()
    if job.get("status") == "running":
        pid = job.get("pid")
        if pid and os.path.exists(f"/proc/{pid}"):
            job["running"] = True
        else:
            job["running"] = False
            job["status"] = "finished"
            save_deploy(job)
    log_text = tail_file(job.get("log_path", "")) if job.get("log_path") else ""
    return jsonify({"job": job, "log_tail": log_text})


@app.route("/myflow/status")
def myflow_status_api():
    return jsonify(myflow_service_status())


@app.route("/myflow/deploy/start", methods=["POST"])
def myflow_deploy_start():
    job = load_myflow_deploy()
    if job.get("status") == "running":
        return jsonify({"ok": False, "error": "Deploy already running."}), 409

    log_path = str(LOG_DIR / f"myflow_deploy_{int(time.time())}.log")
    cmd = (
        "git fetch --all && "
        "git reset --hard origin/main && "
        "git clean -fd && "
        ".venv/bin/pip install -r requirements.txt -q && "
        "sudo /bin/systemctl restart myflow"
    )

    with open(log_path, "a") as log:
        proc = subprocess.Popen(
            ["bash", "-lc", cmd],
            cwd=str(MYFLOW_REPO),
            stdout=log,
            stderr=log,
        )

    job = {
        "status": "running",
        "pid": proc.pid,
        "started_at": int(time.time()),
        "log_path": log_path,
        "cmd": cmd,
    }
    save_myflow_deploy(job)
    return jsonify({"ok": True, "job": job})


@app.route("/myflow/deploy/status")
def myflow_deploy_status():
    job = load_myflow_deploy()
    if job.get("status") == "running":
        pid = job.get("pid")
        if pid and os.path.exists(f"/proc/{pid}"):
            job["running"] = True
        else:
            job["running"] = False
            job["status"] = "finished"
            save_myflow_deploy(job)
    log_text = tail_file(job.get("log_path", "")) if job.get("log_path") else ""
    return jsonify({"job": job, "log_tail": log_text})


@app.route("/scan")
def scan():
    try:
        result = subprocess.run(
            [HANDBRAKE_BIN, "-i", DVD_DEVICE, "-t", "0", "--scan"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            text=True,
        )
        output = result.stdout
    except subprocess.TimeoutExpired as e:
        output = (e.stdout or "")
        output += "\n[scan timed out]"
    parsed = parse_scan_output(output)
    save_scan(parsed)
    return jsonify({
        "output": output[-6000:],
        "titles": parsed["titles"],
        "longest": parsed["longest_title"],
        "dvd_title": parsed["dvd_title"],
    })


@app.route("/handbrake/restart", methods=["POST"])
def restart_handbrake():
    job = load_job()
    pid = job.get("pid")
    if pid and os.path.exists(f"/proc/{pid}"):
        try:
            os.kill(pid, 15)
        except Exception:
            pass
    job["status"] = "idle"
    job["pending_titles"] = []
    job["pid"] = None
    save_job(job)
    return jsonify({"ok": True})


def parse_scan_output(output: str):
    titles = []
    current = None
    longest_title = None
    longest_seconds = -1
    in_subtitle_section = False
    dvd_title = None

    for line in output.splitlines():
        line = line.strip()
        if not dvd_title:
            match = re.search(r"DVD Title:\s*(.+)$", line)
            if match:
                dvd_title = match.group(1).strip()
                continue
        match = re.search(r"scan: scanning title (\d+)", line)
        if match:
            if current:
                titles.append(current)
            number = int(match.group(1))
            current = {
                "number": number,
                "name": f"Title {number}",
                "duration": "unknown",
                "duration_seconds": 0,
                "subtitles": [],
            }
            in_subtitle_section = False
            continue

        if current:
            match = re.search(r"scan: duration is (\d{2}:\d{2}:\d{2})", line)
            if match:
                duration = match.group(1)
                h, m, s = [int(p) for p in duration.split(":")]
                seconds = h * 3600 + m * 60 + s
                current["duration"] = duration
                current["duration_seconds"] = seconds
                if seconds > longest_seconds:
                    longest_seconds = seconds
                    longest_title = current["number"]
                continue

            if "scan: checking subtitle" in line:
                in_subtitle_section = True
                continue
            if "scan: checking audio" in line:
                in_subtitle_section = False
                continue
            if in_subtitle_section:
                match = re.search(r"scan: id=0x[0-9a-f]+, lang=([^,]+)", line)
                if match:
                    label = match.group(1).strip()
                    index = len(current["subtitles"]) + 1
                    current["subtitles"].append(
                        {"index": index, "label": label}
                    )

    if current:
        titles.append(current)

    return {
        "titles": titles,
        "raw": output[-6000:],
        "longest_title": longest_title,
        "dvd_title": dvd_title,
    }


def start_next_title(job):
    if not job.get("pending_titles"):
        job["status"] = "finished"
        return job

    next_item = job["pending_titles"].pop(0)
    title = next_item["number"]
    custom_filename = next_item.get("filename")
    if custom_filename:
        output_file = custom_filename
    elif job.get("multi"):
        output_file = f"{job['base_name']}_T{title}{job['extension']}"
    else:
        output_file = f"{job['base_name']}{job['extension']}"

    output_path = str(Path(job["output_dir"]) / output_file)
    log_path = str(LOG_DIR / f"handbrake_{int(time.time())}_t{title}.log")

    cmd = [
        HANDBRAKE_BIN,
        "-i", DVD_DEVICE,
        "-t", str(title),
        "-o", output_path,
        "--preset", job["preset"],
    ]
    if job.get("subtitle_track") and job["subtitle_track"] != "none":
        cmd += ["--subtitle", str(job["subtitle_track"])]
        if job.get("subtitle_burn"):
            cmd += ["--subtitle-burned"]

    with open(log_path, "a") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=log)

    job["status"] = "running"
    job["pid"] = proc.pid
    job["current_title"] = title
    job["output_path"] = output_path
    job["log_path"] = log_path
    job["cmd"] = " ".join(cmd)
    save_job(job)
    return job


@app.route("/pi/reboot", methods=["POST"])
def reboot_pi():
    subprocess.Popen(["sudo", "/sbin/reboot"])
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001)
