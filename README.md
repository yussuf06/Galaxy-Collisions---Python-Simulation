# Galaxy Encounter / لقاء المجرّات

An educational Python desktop application for exploring two interacting galaxies
with live gravity, dense blue/orange stellar tracers, and a native 3D view.

This is the original clear rendering version. The Heart, Rose, Mice and Penguin
photo-illustration panel has been removed from the interface. Experimental
compound-galaxy/CUDA physics and later spiral-start changes are not included.
The visitor interface is free simulation; older game/illustration modules remain
in the source for compatibility and regression testing.

## Install and run

Use Python 3.11 or 3.12 and a working desktop OpenGL driver. Keep `main.py`,
`requirements.txt`, and `galaxy_app/` together.

```sh
python -m venv .venv
```

Activate the environment:

```text
Windows PowerShell: .\.venv\Scripts\Activate.ps1
Windows cmd:        .venv\Scripts\activate.bat
macOS/Linux:        source .venv/bin/activate
```

Then install and run:

```sh
python -m pip install -r requirements.txt
python -m pip install numba
python main.py
```

Numba is optional CPU acceleration. SciPy is not required. To avoid compilation
or reduce the initial massive-particle count:

```sh
python main.py --fast-start
python main.py --fast-start --no-jit
python main.py --stars-per-galaxy 3000
```

On Windows, after installing dependencies, `pythonw main.py` opens the app without
a console. Shell launchers are also included; leave Windows security settings
unchanged. The old checked-in shortcut refers to a particular computer and is
not a portable installation method.

## Controls

- Space: play/pause; R: reset; N: new random encounter.
- Starting conditions: pass offset, approach speed, mass ratio, and disk tilt,
  with numeric values and explanations. Apply creates a new starting state.
- Encounter presets and an isolated-galaxy control are available.
- Gravity resolution and stars per galaxy control different particle populations.
- Left drag rotates; right drag pans; the wheel zooms. Tracking camera follows
  and smoothly reframes the encounter.
- Brightness, point size, palette and core detail change the view.
- Rewind, PNG screenshots, physical checkpoints, cinema mode and fullscreen
  remain available. C toggles cinema; F toggles fullscreen.
- An Arabic presenter guide is included in the app.

## What is simulated

Massive stellar and live dark-matter samples mutually gravitate in three
dimensions with softened Newtonian forces and fixed-step leapfrog integration.
The default budget is 1,024 massive particles for both galaxies combined and
15,000 visible massless tracer samples per galaxy. Tracers move in an approximate
live field from both galaxies; their force approximation and timestep differ
from those of the massive particles. Their initial spiral appearance is a
presentation distribution, not proof of a self-consistent stable spiral galaxy.

The model has approximate equilibrium and finite-particle heating. It does not
simulate gas, dust, cooling, star formation or a fitted reconstruction of any
observed pair. Time and distance use model units. Blue/orange colours distinguish
particle origin. Camera movement and playback rate do not change the physical
starting conditions or force law. Good energy conservation alone does not prove
physical accuracy or stable initial conditions.

## Verification

```sh
python test_physics.py
python -m unittest test_worker test_worker_dense test_simulation_only test_startup_ui test_view_ui test_reference_ui -v
python main.py --smoke-test
```

Headless Qt tests use the software view; they do not measure native GPU rendering
performance. Optional reference-parity scripts need the developer's original
reference file. Legacy photo assets retain source credits in
`galaxy_app/assets/reference_shapes/`; their panel is not exposed in this UI.

See [README-AR.md](README-AR.md) for Arabic instructions.
