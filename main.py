from fastapi import FastAPI, HTTPException, Path
import os
import shutil
import time
import subprocess
import psutil


PRESET_FOLDER = r"C:\Users\Lab_Dev\Developers\PresetTest"             # folder containing preset1.json/preset2.json/preset3.json
TARGET_FILE   = r"C:\Program Files\Epic Games\UE_5.4\Engine\Plugins\VirtualProduction\Switchboard\Source\Switchboard\configs\MyProject.json"  # the config to overwrite
VALID_PRESETS = {1, 2, 3}

#Switchboard Bat file
SWITCHBOARD_BAT = r"C:\Program Files\Epic Games\UE_5.4\Engine\Plugins\VirtualProduction\Switchboard\Source\Switchboard\Switchboard.bat"

#Incase windows neeeds some processing time
RELAUNCH_DELAY_SECS = 1.5

app = FastAPI(title="Preset Switcher + Switchboard Control", version="1.1.0")

def _preset_path(n: int) -> str:
    return os.path.join(PRESET_FOLDER, f"preset{n}.json")

def _ensure_paths_ok(preset_path: str):
    if not os.path.isdir(PRESET_FOLDER):
        raise HTTPException(status_code=500, detail=f"Preset folder not found: {PRESET_FOLDER}")
    if not os.path.isfile(preset_path):
        raise HTTPException(status_code=404, detail=f"Preset file not found: {preset_path}")
    target_dir = os.path.dirname(TARGET_FILE) or "."
    if not os.path.isdir(target_dir):
        raise HTTPException(status_code=500, detail=f"Target directory does not exist: {target_dir}")

def _switch_config_to(preset: int):
    if preset not in VALID_PRESETS:
        raise HTTPException(status_code=400, detail=f"Invalid preset {preset}. Allowed: {sorted(list(VALID_PRESETS))}")
    preset_file = _preset_path(preset)
    _ensure_paths_ok(preset_file)
    try:
        shutil.copy(preset_file, TARGET_FILE)
    except PermissionError as e:
        raise HTTPException(status_code=500, detail=f"Permission error: {e}")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Filesystem error: {e}")
    return preset_file

def _kill_switchboard() -> list[dict]:
    """
    Kill Switchboard processes by looking for '-m switchboard' in the cmdline.
    Returns a list of killed processes for transparency.
    """
    killed = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = (proc.info.get('name') or "").lower()
            cmdline = " ".join(proc.info.get('cmdline') or []).lower()
            if name == "pythonw.exe" and "-m switchboard" in cmdline:
                print(f"Killing {name} {cmdline} (PID {proc.info['pid']})")
                proc.kill()
                killed.append({"pid": proc.info['pid'], "cmdline": cmdline})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


def _launch_switchboard() -> int:
    if not os.path.isfile(SWITCHBOARD_BAT):
        raise HTTPException(status_code=500, detail=f"Switchboard .bat not found: {SWITCHBOARD_BAT}")


    try:
        creationflags = subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, "CREATE_NEW_CONSOLE") else 0
        p = subprocess.Popen([SWITCHBOARD_BAT], creationflags=creationflags)
        return p.pid
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch Switchboard: {e}")

@app.get("/status")
def status():
    existing = {n: os.path.isfile(_preset_path(n)) for n in VALID_PRESETS}
    return {
        "service": "Preset Switcher + Switchboard Control",
        "target_file": TARGET_FILE,
        "preset_folder": PRESET_FOLDER,
        "presets_found": existing,
        "valid_presets": sorted(list(VALID_PRESETS)),
        "switchboard_bat": SWITCHBOARD_BAT,
    }

# Switch config only
@app.post("/switch/{preset}")
@app.get("/switch/{preset}")  # also allow GET for convenience
def switch_only(preset: int = Path(..., ge=1, le=999)):
    preset_file = _switch_config_to(preset)
    return {
        "action": "switch_only",
        "preset": preset,
        "preset_file": preset_file,
        "target_file": TARGET_FILE,
        "message": f"Switched to preset {preset}."
    }

# Kill only
@app.post("/kill-switchboard")
def kill_only():
    killed = _kill_switchboard()
    return {"action": "kill_switchboard", "killed": killed, "count": len(killed)}

# Launch only
@app.post("/launch-switchboard")
def launch_only():
    pid = _launch_switchboard()
    return {"action": "launch_switchboard", "pid": pid, "message": "Switchboard launching."}

# All-in-one
@app.post("/apply/{preset}")
@app.get("/apply/{preset}")  # allow GET so you can click from a browser
def apply_preset(preset: int = Path(..., ge=1, le=999)):
    killed = _kill_switchboard()
    preset_file = _switch_config_to(preset)
    time.sleep(RELAUNCH_DELAY_SECS)
    pid = _launch_switchboard()
    return {
        "action": "apply",
        "preset": preset,
        "preset_file": preset_file,
        "target_file": TARGET_FILE,
        "killed": killed,
        "launched_pid": pid,
        "message": f"Killed Switchboard ({len(killed)} procs), switched to preset {preset}, relaunched."
    }

# If you prefer running this file directly: python main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
