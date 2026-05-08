# Pi Hub — Windows launchers

These scripts make the **Pi SSH** and **PiSSD** buttons in Pi Hub work. They run on
your Windows PC (the browser client), not on the Pi.

## One-time setup

1. Install PuTTY (for `plink.exe`): https://www.putty.org/
   - Make sure `C:\Program Files\PuTTY` is on your PATH.
2. Double-click `install.bat`. It registers two custom URL protocols:
   - `pissh://` → opens a terminal logged in to the Pi
   - `pissd://` → opens Explorer at `\\mpk-pi\PiSSD`
3. Restart your browser.

The first time you click each button, the browser will ask "Open Pi SSH Protocol?" —
check **Always allow** and click Open.

## Files

- `install.bat` — registers the protocols (no admin rights needed; uses HKCU)
- `uninstall.bat` — removes them
- `open-ssh.bat` — launches the SSH terminal (called by `pissh://`)
- `open-pissd.bat` — opens Explorer (called by `pissd://`)

## Notes

- The Pi password lives in `open-ssh.bat`. Local network only — keep this folder off shared drives.
- If you move the `pi_hub` folder, re-run `install.bat` to update the registered paths.
- First SSH connection will prompt to cache the host key — type `y` and press Enter once.
