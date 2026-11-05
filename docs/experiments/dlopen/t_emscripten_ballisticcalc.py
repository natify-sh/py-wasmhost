import sys, importlib.machinery as m
sfx = ".cpython-315-wasm32-emscripten.so"
sys.path_hooks.insert(0, m.FileFinder.path_hook((m.ExtensionFileLoader, m.EXTENSION_SUFFIXES + [sfx]), (m.SourceFileLoader, m.SOURCE_SUFFIXES), (m.SourcelessFileLoader, m.BYTECODE_SUFFIXES)))
sys.path_importer_cache.clear()
import py_ballisticcalc_exts as e
print(e.__file__, flush=True)
from py_ballisticcalc_exts import traj_data
print("traj_data ok", flush=True)
from py_ballisticcalc_exts import base_engine
print("base_engine ok", flush=True)
from py_ballisticcalc_exts import engines
print("engines ok", [n for n in dir(engines) if not n.startswith("_")][:8], flush=True)
from py_ballisticcalc import *
from py_ballisticcalc.interface import Calculator
from py_ballisticcalc.unit import Distance, Velocity, Weight, Angular
import py_ballisticcalc as bc
print("engines:", bc.__version__ if hasattr(bc, "__version__") else "?", flush=True)
dm = DragModel(0.223, TableG7, Weight.Grain(168), Distance.Inch(0.308), Distance.Inch(1.282))
ammo = Ammo(dm, Velocity.FPS(2750))
weapon = Weapon(Distance.Inch(2), Distance.Inch(12))
shot = Shot(weapon=weapon, ammo=ammo)
for eng in ("rk4_engine", "cythonized_rk4_engine"):
    try:
        calc = Calculator(engine=eng)
        calc.set_weapon_zero(shot, Distance.Yard(100))
        hold = calc.fire(shot, trajectory_range=Distance.Yard(1000), trajectory_step=Distance.Yard(500))
        print(eng, [ (round(p.distance >> Distance.Yard,0), round(p.height >> Distance.Inch,3), round(p.velocity >> Velocity.FPS,2)) for p in hold], flush=True)
    except Exception as ex:
        print(eng, "FAILED", type(ex).__name__, ex, flush=True)
