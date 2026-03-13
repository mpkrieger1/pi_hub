# Pi Hub

Simple web UI to monitor the Pi and run HandBrakeCLI.

## Install
```
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Run (manual)
```
. .venv/bin/activate
python app.py
```
Open: `http://mpk-pi:3001`

## Run as a service
```
sudo cp /home/mpkrieger1/hub/pi-hub.service /etc/systemd/system/pi-hub.service
sudo systemctl daemon-reload
sudo systemctl enable --now pi-hub
```

## Notes
- Output defaults to `/mnt/ssd/Movies` (Windows: `\\mpk-pi\PiSSD\Movies`).
- Only folders listed in `ALLOWED_OUTPUT_DIRS` can be used.
