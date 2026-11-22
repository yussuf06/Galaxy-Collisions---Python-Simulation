"""Native proof of the visitor game, same live gravity and reference renderer.

Run with the existing Windows interpreter. A short visible test window opens;
the script saves proof PNGs and photo-native-verification.json beside itself.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from galaxy_app.window import MainWindow


def run():
    if os.environ.get('QT_QPA_PLATFORM','').lower() in ('offscreen','minimal'):
        raise RuntimeError('Native photo verification requires the desktop OpenGL backend.')
    app=QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    folder=Path(__file__).resolve().parent
    errors=[];captures=[];evidence_calls=[]
    old_hook=sys.excepthook;old_warning=QMessageBox.warning
    sys.excepthook=lambda *error:errors.append(repr(error))
    QMessageBox.warning=lambda *args:errors.append(str(args[-1]))
    window=MainWindow({'count':512,'tracer_count':15000})
    window.resize(1440,900);window.show();window.raise_();window.activateWindow()
    window.worker.message.connect(lambda msg:captures.append(msg) if msg['type']=='photo_capture' else None)
    original_evidence=window.view.set_photo_evidence
    def evidence(positions,objective='tidal'):
        evidence_calls.append((np.empty((0,3)) if positions is None else np.asarray(positions).copy(),objective))
        return original_evidence(positions,objective)
    window.view.set_photo_evidence=evidence
    stage='startup';started=time.monotonic();result=1;report={};closed_at=None;frozen_capture=None;preset_ready_at=None

    def finish(success):
        nonlocal result,stage,closed_at
        result=0 if success else 1;stage='closing';closed_at=time.monotonic();window.close()

    def tick():
        nonlocal stage,report,frozen_capture,preset_ready_at
        try:
            if stage=='closing':
                if not window.thread.isRunning():timer.stop();app.quit()
                elif time.monotonic()-closed_at>12:
                    print('FAIL: Worker did not shut down',flush=True);timer.stop();app.exit(1)
                return
            if errors:raise AssertionError(errors)
            if time.monotonic()-started>85:raise AssertionError('Native photo test timed out: '+window.status.text())
            frame=window.frame
            if stage=='startup' and frame is not None and not window.busy:
                assert hasattr(window.view,'canvas')
                assert window.view.canvas.native.context().isValid()
                assert not hasattr(window.view,'glow_visual')
                assert window.view.canvas.context.config['samples']==0
                assert window.view.exposure==1. and window.view.star_size==1.
                window.mode_combo.setCurrentIndex(3);stage='preparing_photo'
            elif stage=='preparing_photo' and not window.busy and frame['mode']=='photo':
                assert frame['photo']['objective']=='tidal'
                assert len(frame['tracer_positions'])==30000
                assert window.photo_button.isVisible()
                window.grab().save(str(folder/'photo-native-window.png'))
                window.view.capture().save(str(folder/'photo-native-ready.png'))
                window.rate.setCurrentIndex(window.rate.findData(4.))
                window.photo_button.click();stage='watching'
            elif stage=='watching' and frame['phase']=='running' and frame['time']>=12.:
                window.photo_button.click();stage='capturing'
            elif stage=='capturing' and captures and frame['phase'] in ('paused','ended'):
                captured=captures[-1]
                assert captured['objective']=='tidal'
                assert captured['source']=='tracers'
                assert captured['feature_count']>=2,captured
                assert captured['score']>0,captured
                assert np.isfinite(captured['feature_positions']).all()
                assert any(len(points)>0 for points,_ in evidence_calls), 'No actual evidence overlay was requested'
                image=window.view.capture();assert not image.isNull()
                image.save(str(folder/'photo-native-capture.png'))
                window.grab().save(str(folder/'photo-native-result-window.png'))
                report=dict(result='PASS',renderer=window.view.gpu_renderer,
                            framebuffer=list(window.view.canvas.physical_size),
                            visible_stars=len(frame['tracer_positions']),gravity_particles=frame['count'],
                            objective=captured['objective'],score=captured['score'],
                            feature_count=captured['feature_count'],source=captured['source'],
                            captured_model_time=captured['time'],reference_style_preserved=True,
                            evidence_overlay_requested=True)
                frozen_capture=dict(time=frame['time'],positions=frame['positions'].copy(),
                                    tracers=frame['tracer_positions'].copy(),shots=frame['photo']['shot_count'])
                assert window.photo_replay_button.isVisible()
                window.photo_replay_button.click();stage='tail_replay'
            elif stage=='tail_replay' and window._photo_replay is None:
                assert frame['phase']=='paused'
                assert frame['time']==frozen_capture['time']
                assert np.array_equal(frame['positions'],frozen_capture['positions'])
                assert np.array_equal(frame['tracer_positions'],frozen_capture['tracers'])
                assert frame['photo']['shot_count']==frozen_capture['shots']
                assert window.view.data['time']==frame['time']
                report['history_replay_preserves_physics_and_attempts']=True
                window.photo_next_button.click();stage='next_mission'
            elif stage=='next_mission' and not window.busy and frame['photo']['objective']=='bridge':
                assert frame['phase']=='ready'
                assert frame['photo']['shot_count']==0
                report['next_mission']='bridge'
                window.photo_button.click();stage='bridge_watching'
            elif stage=='bridge_watching' and frame['phase']=='running' and frame['time']>=9.5:
                window.photo_button.click();stage='bridge_capturing'
            elif stage=='bridge_capturing' and captures[-1]['objective']=='bridge' and frame['phase'] in ('paused','ended'):
                captured=captures[-1]
                assert captured['source']=='tracers'
                assert captured['feature_count']>=2,captured
                assert captured['score']>0 and captured['success'],captured
                assert len(captured['feature_positions'])>0
                assert np.isfinite(captured['feature_positions']).all()
                window.view.capture().save(str(folder/'photo-native-bridge-capture.png'))
                window.grab().save(str(folder/'photo-native-bridge-window.png'))
                report['bridge']=dict(score=captured['score'],feature_count=captured['feature_count'],
                                      success=captured['success'],time=captured['time'],source=captured['source'])
                window.mode_combo.setCurrentIndex(0);stage='show_presets'
            elif stage=='show_presets' and not window.busy and frame['mode']=='simulation':
                if preset_ready_at is None:preset_ready_at=time.monotonic();return
                if time.monotonic()-preset_ready_at<.25:return
                assert window.encounter_combo.isVisible()
                assert not window.custom_settings.isVisible()
                assert not window.photo_button.isVisible()
                window.view.capture().save(str(folder/'photo-native-presets-scene.png'))
                window.grab().save(str(folder/'photo-native-presets-window.png'))
                report['named_presets_available']=window.encounter_combo.count()-1
                report['advanced_conditions_hidden_by_default']=True
                (folder/'photo-native-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                print(json.dumps(report),flush=True);finish(True)
        except Exception as exc:
            print('FAIL: '+repr(exc),flush=True)
            finish(False)

    timer=QTimer();timer.setInterval(50);timer.timeout.connect(tick);timer.start()
    try:app.exec()
    finally:
        sys.excepthook=old_hook;QMessageBox.warning=old_warning
    return result


if __name__=='__main__':raise SystemExit(run())
