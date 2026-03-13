import os
import re
import json
import time
import shutil
import subprocess
from pathlib import Path

import requests as http_requests
from flask import Flask, render_template, request, jsonify, Response

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
APPS_DIR = Path("/home/mpkrieger1/apps")
APPS_CONFIG = DATA_DIR / "apps.json"

FILE_ROOTS = {
    "Downloads": Path("/mnt/ssd/downloads"),
    "Movies": Path("/mnt/ssd/Movies"),
}

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


def nordvpn_status():
    """Get NordVPN connection status."""
    info = {"connected": False, "status": "unknown", "country": None, "ip": None}
    try:
        result = subprocess.run(
            ["nordvpn", "status"],
            capture_output=True, text=True, timeout=5,
        )
        output = result.stdout
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Status:"):
                val = line.split(":", 1)[1].strip()
                info["status"] = val
                info["connected"] = "connect" in val.lower()
            elif line.startswith("Country:"):
                info["country"] = line.split(":", 1)[1].strip()
            elif line.startswith("Server IP:") or line.startswith("IP:"):
                info["ip"] = line.split(":", 1)[1].strip()
            elif line.startswith("City:"):
                info["city"] = line.split(":", 1)[1].strip()
    except Exception:
        pass
    return info


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
        vpn=nordvpn_status(),
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


@app.route("/vpn/status")
def vpn_status_api():
    return jsonify(nordvpn_status())


@app.route("/vpn/connect", methods=["POST"])
def vpn_connect():
    country = request.form.get("country", "").strip()
    cmd = ["nordvpn", "connect"]
    if country:
        cmd.append(country)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        return jsonify({"ok": result.returncode == 0, "output": output.strip()})
    except Exception as e:
        return jsonify({"ok": False, "output": str(e)}), 500


@app.route("/vpn/disconnect", methods=["POST"])
def vpn_disconnect():
    try:
        result = subprocess.run(
            ["nordvpn", "disconnect"],
            capture_output=True, text=True, timeout=15,
        )
        output = result.stdout + result.stderr
        return jsonify({"ok": result.returncode == 0, "output": output.strip()})
    except Exception as e:
        return jsonify({"ok": False, "output": str(e)}), 500


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


# ═══════════════════════════════════════════════════════════════
# APP MANAGER
# ═══════════════════════════════════════════════════════════════

def load_apps():
    if APPS_CONFIG.exists():
        try:
            return json.loads(APPS_CONFIG.read_text())
        except Exception:
            return {}
    return {}


def save_apps(apps):
    APPS_CONFIG.write_text(json.dumps(apps, indent=2))


def app_deploy_file(slug):
    return JOBS_DIR / f"app_deploy_{slug}.json"


def load_app_deploy(slug):
    f = app_deploy_file(slug)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            return {"status": "idle"}
    return {"status": "idle"}


def save_app_deploy(slug, job):
    app_deploy_file(slug).write_text(json.dumps(job, indent=2))


def get_app_status(app_config):
    """Get live status for a managed app."""
    slug = app_config["slug"]
    info = dict(app_config)
    info["service_status"] = "unknown"
    info["active"] = False
    info["commit"] = None
    info["commit_msg"] = None
    info["commit_age"] = None

    service = app_config.get("service_name")
    if service:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True, text=True, timeout=5,
            )
            status = result.stdout.strip()
            info["service_status"] = status
            info["active"] = status == "active"
        except Exception:
            pass

    repo_dir = app_config.get("repo_dir")
    if repo_dir and Path(repo_dir).exists():
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%H|%s|%ar"],
                capture_output=True, text=True, timeout=5,
                cwd=repo_dir,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split("|", 2)
                if len(parts) == 3:
                    info["commit"] = parts[0][:8]
                    info["commit_msg"] = parts[1]
                    info["commit_age"] = parts[2]
        except Exception:
            pass

    return info


@app.route("/apps")
def apps_page():
    apps = load_apps()
    app_list = []
    for slug, cfg in apps.items():
        cfg["slug"] = slug
        app_list.append(get_app_status(cfg))
    return render_template("apps.html", app_name=APP_NAME, apps=app_list)


@app.route("/apps/list")
def apps_list_api():
    apps = load_apps()
    result = []
    for slug, cfg in apps.items():
        cfg["slug"] = slug
        result.append(get_app_status(cfg))
    return jsonify(result)


@app.route("/apps/create", methods=["POST"])
def apps_create():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    repo_url = data.get("repo_url", "").strip()
    port = data.get("port", "").strip()
    app_type = data.get("app_type", "python")  # python, node, static
    start_cmd = data.get("start_cmd", "").strip()
    public_url = data.get("public_url", "").strip()

    if not name or not repo_url:
        return jsonify({"ok": False, "error": "Name and repo URL required."}), 400

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        return jsonify({"ok": False, "error": "Invalid name."}), 400

    apps = load_apps()
    if slug in apps:
        return jsonify({"ok": False, "error": f"App '{slug}' already exists."}), 409

    app_dir = str(APPS_DIR / slug)
    repo_dir = str(APPS_DIR / slug / "repo")

    # Build the deploy command
    setup_cmds = [f"mkdir -p {app_dir}"]
    setup_cmds.append(f"git clone {repo_url} {repo_dir}")

    if app_type == "python":
        setup_cmds.append(f"cd {repo_dir} && python3 -m venv .venv")
        setup_cmds.append(f"cd {repo_dir} && .venv/bin/pip install --upgrade pip -q")
        setup_cmds.append(f"cd {repo_dir} && .venv/bin/pip install -r requirements.txt -q")
    elif app_type == "node":
        setup_cmds.append(f"cd {repo_dir} && npm install")

    # Determine the start command for systemd
    if not start_cmd:
        if app_type == "python":
            start_cmd = f"{repo_dir}/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port {port or '8000'}"
        elif app_type == "node":
            start_cmd = f"npm start"

    service_name = f"app-{slug}"

    # Build systemd service content
    service_content = f"""[Unit]
Description={name}
After=network.target

[Service]
User=mpkrieger1
WorkingDirectory={repo_dir}
ExecStart={start_cmd}
Restart=on-failure
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""

    full_cmd = " && ".join(setup_cmds)
    full_cmd += f' && echo \'{service_content}\' | sudo tee /etc/systemd/system/{service_name}.service > /dev/null'
    full_cmd += f" && sudo systemctl daemon-reload && sudo systemctl enable {service_name} && sudo systemctl start {service_name}"

    log_path = str(LOG_DIR / f"app_create_{slug}_{int(time.time())}.log")

    with open(log_path, "a") as log:
        proc = subprocess.Popen(
            ["bash", "-lc", full_cmd],
            stdout=log, stderr=log,
        )

    deploy_job = {
        "status": "running",
        "pid": proc.pid,
        "started_at": int(time.time()),
        "log_path": log_path,
        "action": "create",
    }
    save_app_deploy(slug, deploy_job)

    apps[slug] = {
        "name": name,
        "repo_url": repo_url,
        "repo_dir": repo_dir,
        "app_dir": app_dir,
        "port": port or "",
        "app_type": app_type,
        "start_cmd": start_cmd,
        "service_name": service_name,
        "public_url": public_url,
        "created_at": int(time.time()),
    }
    save_apps(apps)

    return jsonify({"ok": True, "slug": slug, "job": deploy_job})


@app.route("/apps/<slug>/pull", methods=["POST"])
def apps_pull(slug):
    apps = load_apps()
    if slug not in apps:
        return jsonify({"ok": False, "error": "App not found."}), 404

    cfg = apps[slug]
    repo_dir = cfg["repo_dir"]
    app_type = cfg.get("app_type", "python")
    service_name = cfg.get("service_name", f"app-{slug}")

    cmds = [
        f"cd {repo_dir}",
        "git fetch --all",
        "git reset --hard origin/main",
        "git clean -fd",
    ]
    if app_type == "python":
        cmds.append(".venv/bin/pip install -r requirements.txt -q")
    elif app_type == "node":
        cmds.append("npm install")

    cmds.append(f"sudo /bin/systemctl restart {service_name}")

    log_path = str(LOG_DIR / f"app_pull_{slug}_{int(time.time())}.log")
    full_cmd = " && ".join(cmds)

    with open(log_path, "a") as log:
        proc = subprocess.Popen(
            ["bash", "-lc", full_cmd],
            cwd=repo_dir, stdout=log, stderr=log,
        )

    job = {
        "status": "running",
        "pid": proc.pid,
        "started_at": int(time.time()),
        "log_path": log_path,
        "action": "pull",
    }
    save_app_deploy(slug, job)
    return jsonify({"ok": True, "job": job})


@app.route("/apps/<slug>/start", methods=["POST"])
def apps_start(slug):
    apps = load_apps()
    if slug not in apps:
        return jsonify({"ok": False, "error": "App not found."}), 404
    service = apps[slug].get("service_name", f"app-{slug}")
    try:
        subprocess.run(["sudo", "/bin/systemctl", "start", service], timeout=10)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/apps/<slug>/stop", methods=["POST"])
def apps_stop(slug):
    apps = load_apps()
    if slug not in apps:
        return jsonify({"ok": False, "error": "App not found."}), 404
    service = apps[slug].get("service_name", f"app-{slug}")
    try:
        subprocess.run(["sudo", "/bin/systemctl", "stop", service], timeout=10)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/apps/<slug>/restart", methods=["POST"])
def apps_restart(slug):
    apps = load_apps()
    if slug not in apps:
        return jsonify({"ok": False, "error": "App not found."}), 404
    service = apps[slug].get("service_name", f"app-{slug}")
    try:
        subprocess.run(["sudo", "/bin/systemctl", "restart", service], timeout=10)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/apps/<slug>/deploy-status")
def apps_deploy_status(slug):
    job = load_app_deploy(slug)
    if job.get("status") == "running":
        pid = job.get("pid")
        if pid and os.path.exists(f"/proc/{pid}"):
            job["running"] = True
        else:
            job["running"] = False
            job["status"] = "finished"
            save_app_deploy(slug, job)
    log_text = tail_file(job.get("log_path", "")) if job.get("log_path") else ""
    return jsonify({"job": job, "log_tail": log_text})


@app.route("/apps/<slug>/delete", methods=["POST"])
def apps_delete(slug):
    apps = load_apps()
    if slug not in apps:
        return jsonify({"ok": False, "error": "App not found."}), 404

    cfg = apps[slug]
    service = cfg.get("service_name", f"app-{slug}")

    # Stop and disable service
    try:
        subprocess.run(["sudo", "/bin/systemctl", "stop", service], timeout=10)
        subprocess.run(["sudo", "/bin/systemctl", "disable", service], timeout=10)
        subprocess.run(["sudo", "rm", f"/etc/systemd/system/{service}.service"], timeout=5)
        subprocess.run(["sudo", "/bin/systemctl", "daemon-reload"], timeout=10)
    except Exception:
        pass

    del apps[slug]
    save_apps(apps)
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════
# FILE MANAGER
# ═══════════════════════════════════════════════════════════════

def _resolve_file_path(root_key, rel_path):
    """Resolve a relative path within an allowed root. Returns None if invalid."""
    if root_key not in FILE_ROOTS:
        return None
    root = FILE_ROOTS[root_key]
    clean = Path(rel_path.replace("\\", "/")).parts
    # Reject any '..' components
    if ".." in clean:
        return None
    resolved = root.joinpath(*clean) if clean else root
    # Ensure it's still under the root
    try:
        resolved.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def _file_info(path):
    """Build a file/dir info dict."""
    stat = path.stat()
    return {
        "name": path.name,
        "is_dir": path.is_dir(),
        "size": stat.st_size if path.is_file() else None,
        "modified": int(stat.st_mtime),
    }


@app.route("/files")
def files_page():
    roots = {k: str(v) for k, v in FILE_ROOTS.items()}
    return render_template("files.html", app_name=APP_NAME, roots=roots)


@app.route("/files/browse")
def files_browse():
    root_key = request.args.get("root", "")
    rel = request.args.get("path", "")

    if not root_key or root_key not in FILE_ROOTS:
        return jsonify({"ok": False, "error": "Invalid root."}), 400

    target = _resolve_file_path(root_key, rel)
    if target is None or not target.exists() or not target.is_dir():
        return jsonify({"ok": False, "error": "Directory not found."}), 404

    items = []
    try:
        for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                items.append(_file_info(entry))
            except Exception:
                pass
    except PermissionError:
        return jsonify({"ok": False, "error": "Permission denied."}), 403

    return jsonify({
        "ok": True,
        "root": root_key,
        "path": rel,
        "items": items,
    })


@app.route("/files/rename", methods=["POST"])
def files_rename():
    data = request.get_json() or {}
    root_key = data.get("root", "")
    rel = data.get("path", "")
    new_name = data.get("new_name", "").strip()

    if not new_name or "/" in new_name or "\\" in new_name or ".." in new_name:
        return jsonify({"ok": False, "error": "Invalid name."}), 400

    target = _resolve_file_path(root_key, rel)
    if target is None or not target.exists():
        return jsonify({"ok": False, "error": "File not found."}), 404

    new_path = target.parent / new_name
    if new_path.exists():
        return jsonify({"ok": False, "error": "A file with that name already exists."}), 409

    target.rename(new_path)
    return jsonify({"ok": True})


@app.route("/files/move", methods=["POST"])
def files_move():
    data = request.get_json() or {}
    root_key = data.get("root", "")
    rel = data.get("path", "")
    dest_rel = data.get("dest", "")

    target = _resolve_file_path(root_key, rel)
    dest_dir = _resolve_file_path(root_key, dest_rel)
    if target is None or not target.exists():
        return jsonify({"ok": False, "error": "Source not found."}), 404
    if dest_dir is None or not dest_dir.is_dir():
        return jsonify({"ok": False, "error": "Destination folder not found."}), 404

    new_path = dest_dir / target.name
    if new_path.exists():
        return jsonify({"ok": False, "error": "File already exists in destination."}), 409

    shutil.move(str(target), str(new_path))
    return jsonify({"ok": True})


@app.route("/files/delete", methods=["POST"])
def files_delete():
    data = request.get_json() or {}
    root_key = data.get("root", "")
    rel = data.get("path", "")

    target = _resolve_file_path(root_key, rel)
    if target is None or not target.exists():
        return jsonify({"ok": False, "error": "File not found."}), 404

    # Don't allow deleting the root itself
    if target.resolve() == FILE_ROOTS[root_key].resolve():
        return jsonify({"ok": False, "error": "Cannot delete root directory."}), 400

    if target.is_dir():
        shutil.rmtree(str(target))
    else:
        target.unlink()
    return jsonify({"ok": True})


@app.route("/files/mkdir", methods=["POST"])
def files_mkdir():
    data = request.get_json() or {}
    root_key = data.get("root", "")
    rel = data.get("path", "")
    name = data.get("name", "").strip()

    if not name or "/" in name or "\\" in name or ".." in name:
        return jsonify({"ok": False, "error": "Invalid folder name."}), 400

    parent = _resolve_file_path(root_key, rel)
    if parent is None or not parent.is_dir():
        return jsonify({"ok": False, "error": "Parent directory not found."}), 404

    new_dir = parent / name
    if new_dir.exists():
        return jsonify({"ok": False, "error": "Already exists."}), 409

    new_dir.mkdir()
    return jsonify({"ok": True})


@app.route("/files/upload", methods=["POST"])
def files_upload():
    root_key = request.form.get("root", "")
    rel = request.form.get("path", "")

    target_dir = _resolve_file_path(root_key, rel)
    if target_dir is None or not target_dir.is_dir():
        return jsonify({"ok": False, "error": "Upload directory not found."}), 404

    uploaded = []
    for f in request.files.getlist("files"):
        if not f.filename:
            continue
        safe_name = re.sub(r"[^\w\s\-\.\(\)]", "_", f.filename.strip())
        dest = target_dir / safe_name
        f.save(str(dest))
        uploaded.append(safe_name)

    return jsonify({"ok": True, "uploaded": uploaded})


@app.route("/files/download")
def files_download():
    from flask import send_file
    root_key = request.args.get("root", "")
    rel = request.args.get("path", "")

    target = _resolve_file_path(root_key, rel)
    if target is None or not target.exists() or not target.is_file():
        return jsonify({"ok": False, "error": "File not found."}), 404

    return send_file(str(target), as_attachment=True)


# ═══════════════════════════════════════════════════════════════
# DOCKER MANAGER
# ═══════════════════════════════════════════════════════════════

@app.route("/docker")
def docker_page():
    return render_template("docker.html", app_name=APP_NAME)


@app.route("/docker/list")
def docker_list():
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format",
             '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}","state":"{{.State}}","status":"{{.Status}}","ports":"{{.Ports}}"}'],
            capture_output=True, text=True, timeout=10,
        )
        containers = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            try:
                c = json.loads(line)
                # Parse ports into a clean list
                raw_ports = c.get("ports", "")
                c["ports"] = [p.strip() for p in raw_ports.split(",") if p.strip()] if raw_ports else []
                containers.append(c)
            except json.JSONDecodeError:
                pass
        return jsonify(containers)
    except Exception as e:
        return jsonify([])


@app.route("/docker/start", methods=["POST"])
def docker_start():
    data = request.get_json() or {}
    cid = data.get("id", "").strip()
    if not cid:
        return jsonify({"ok": False, "error": "No container ID."}), 400
    try:
        result = subprocess.run(["docker", "start", cid], capture_output=True, text=True, timeout=30)
        return jsonify({"ok": result.returncode == 0, "output": result.stdout + result.stderr})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/docker/stop", methods=["POST"])
def docker_stop():
    data = request.get_json() or {}
    cid = data.get("id", "").strip()
    if not cid:
        return jsonify({"ok": False, "error": "No container ID."}), 400
    try:
        result = subprocess.run(["docker", "stop", cid], capture_output=True, text=True, timeout=30)
        return jsonify({"ok": result.returncode == 0, "output": result.stdout + result.stderr})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/docker/restart", methods=["POST"])
def docker_restart():
    data = request.get_json() or {}
    cid = data.get("id", "").strip()
    if not cid:
        return jsonify({"ok": False, "error": "No container ID."}), 400
    try:
        result = subprocess.run(["docker", "restart", cid], capture_output=True, text=True, timeout=30)
        return jsonify({"ok": result.returncode == 0, "output": result.stdout + result.stderr})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/docker/remove", methods=["POST"])
def docker_remove():
    data = request.get_json() or {}
    cid = data.get("id", "").strip()
    if not cid:
        return jsonify({"ok": False, "error": "No container ID."}), 400
    try:
        # Stop first, then remove
        subprocess.run(["docker", "stop", cid], capture_output=True, text=True, timeout=30)
        result = subprocess.run(["docker", "rm", cid], capture_output=True, text=True, timeout=15)
        return jsonify({"ok": result.returncode == 0, "output": result.stdout + result.stderr})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/docker/logs")
def docker_logs():
    cid = request.args.get("id", "").strip()
    lines = request.args.get("lines", "100").strip()
    if not cid:
        return jsonify({"logs": "No container ID."}), 400
    if not lines.isdigit():
        lines = "100"
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", lines, cid],
            capture_output=True, text=True, timeout=10,
        )
        return jsonify({"logs": result.stdout + result.stderr})
    except Exception as e:
        return jsonify({"logs": str(e)})


@app.route("/docker/install", methods=["POST"])
def docker_install():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    image = data.get("image", "").strip()
    ports = data.get("ports", [])
    volumes = data.get("volumes", [])
    env = data.get("env", [])
    network = data.get("network", "")
    restart = data.get("restart", "unless-stopped")

    if not name or not image:
        return jsonify({"ok": False, "error": "Name and image are required."}), 400

    # Validate name: alphanumeric, hyphens, underscores only
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return jsonify({"ok": False, "error": "Invalid container name."}), 400

    # Pull image first
    try:
        pull_result = subprocess.run(
            ["docker", "pull", image],
            capture_output=True, text=True, timeout=300,
        )
        if pull_result.returncode != 0:
            return jsonify({"ok": False, "error": "Pull failed: " + pull_result.stderr}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Image pull timed out (5 min)."}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    # Build docker run command
    cmd = ["docker", "run", "-d", "--name", name]

    if restart:
        cmd += ["--restart", restart]
    if network:
        cmd += ["--network", network]
    for p in ports:
        p = p.strip()
        if p:
            cmd += ["-p", p]
    for v in volumes:
        v = v.strip()
        if v:
            cmd += ["-v", v]
    for e_var in env:
        e_var = e_var.strip()
        if e_var:
            cmd += ["-e", e_var]

    cmd.append(image)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return jsonify({"ok": True, "container_id": result.stdout.strip()})
        else:
            return jsonify({"ok": False, "error": result.stderr.strip()}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# SYSTEM LOG VIEWER
# ═══════════════════════════════════════════════════════════════

VIEWABLE_LOGS = {
    "syslog": "/var/log/syslog",
    "pi-hub": "__journalctl:pi-hub",
    "myflow": "__journalctl:myflow",
    "baseball-sim": "__journalctl:baseball_sim",
    "docker": "__journalctl:docker",
    "auth": "/var/log/auth.log",
}


@app.route("/logs/sources")
def log_sources():
    return jsonify(list(VIEWABLE_LOGS.keys()))


@app.route("/logs/view")
def log_view():
    source = request.args.get("source", "").strip()
    lines = request.args.get("lines", "100").strip()
    if source not in VIEWABLE_LOGS:
        return jsonify({"logs": "Unknown log source."}), 400
    if not lines.isdigit():
        lines = "100"

    target = VIEWABLE_LOGS[source]

    try:
        if target.startswith("__journalctl:"):
            unit = target.split(":", 1)[1]
            result = subprocess.run(
                ["journalctl", "-u", unit, "-n", lines, "--no-pager"],
                capture_output=True, text=True, timeout=10,
            )
        else:
            result = subprocess.run(
                ["tail", "-n", lines, target],
                capture_output=True, text=True, timeout=10,
            )
        return jsonify({"logs": result.stdout + result.stderr})
    except Exception as e:
        return jsonify({"logs": str(e)})


# ═══════════════════════════════════════════════════════════════
# QBITTORRENT PROXY
# ═══════════════════════════════════════════════════════════════

QBT_UPSTREAM = "http://127.0.0.1:8080"

@app.route("/qbt")
@app.route("/qbt/")
def qbt_index():
    """Serve the qBittorrent Web UI through the hub."""
    return _proxy_qbt("")

@app.route("/qbt/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def qbt_proxy(subpath):
    return _proxy_qbt(subpath)

def _proxy_qbt(subpath):
    url = f"{QBT_UPSTREAM}/{subpath}"
    if request.query_string:
        url += "?" + request.query_string.decode()

    headers = {k: v for k, v in request.headers if k.lower() not in ("host", "transfer-encoding")}

    try:
        resp = http_requests.request(
            method=request.method,
            url=url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=30,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"Cannot reach qBittorrent: {e}"}), 502

    # Build response, rewriting Location headers and cookie paths
    excluded_headers = {"transfer-encoding", "content-encoding", "content-length"}
    resp_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded_headers]

    # Rewrite Location header to add /qbt prefix
    final_headers = []
    for k, v in resp_headers:
        if k.lower() == "location" and v.startswith("/"):
            v = "/qbt" + v
        final_headers.append((k, v))

    return Response(resp.content, status=resp.status_code, headers=final_headers)


@app.route("/pi/reboot", methods=["POST"])
def reboot_pi():
    subprocess.Popen(["sudo", "/sbin/reboot"])
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001)
