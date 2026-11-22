#!/usr/bin/env python3
"""Galaxy Encounter desktop: one Python app for simulation and randomized game."""
from __future__ import annotations
import argparse,sys,logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke-test',action='store_true',help='Run a headless Qt application and physics smoke test')
    parser.add_argument('--fast-start',action='store_true',help='Start at 512 particles; the same physics and full controls remain available')
    parser.add_argument('--no-jit',action='store_true',help='Use the NumPy solver throughout the app, avoiding JIT compilation')
    parser.add_argument('--stars-per-galaxy',type=int,choices=[3000,7500,15000,30000],default=15000,
                        help='Visible reference spiral stars per galaxy (default: 15000)')
    args=parser.parse_args()
    log_dir=Path(__file__).resolve().parent/'logs'
    try:
        log_dir.mkdir(exist_ok=True)
        handler=RotatingFileHandler(log_dir/'galaxy-encounter.log',maxBytes=1_000_000,backupCount=2,encoding='utf-8')
    except OSError:
        handler=logging.StreamHandler()
    logging.basicConfig(level=logging.INFO,handlers=[handler],format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    if args.smoke_test:
        from galaxy_app.smoke_test import run
        return run()
    try:
        from PySide6.QtWidgets import QApplication
        from galaxy_app.window import MainWindow
    except ImportError as exc:
        print(f'Missing dependency: {exc}\nUse the launcher for your operating system, or run: python -m pip install -r requirements.txt',file=sys.stderr)
        return 1
    app=QApplication(sys.argv);app.setApplicationName('Galaxy Encounter Python')
    startup_config={'tracer_count':args.stars_per_galaxy}
    if args.fast_start:startup_config['count']=512
    if args.no_jit:startup_config['backend']='numpy'
    window=MainWindow(startup_config);window.show();return app.exec()

if __name__=='__main__':raise SystemExit(main())
