"""Qt worker: all simulation and challenge scoring run on Python N-body physics."""
from __future__ import annotations
from collections import deque
import json, math, time, threading, logging, traceback
from pathlib import Path
import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal, Slot, QThread
from .physics import NBody
from .dense_stars import DenseStars
from .photo_hunt import PhotoHunt, OBJECTIVES
from .shape_presets import get_shape,shape_config

END_TIME = 30.0

class PreparationCancelled(Exception):
    """Cooperative cancellation between physics preparation stages."""

class PhysicsWorker(QObject):
    message = Signal(object)
    def __init__(self, startup_config=None):
        super().__init__()
        self.startup_config = dict(startup_config or {})
        self.simulation_only = bool(self.startup_config.pop('simulation_only', False))
        self.force_numpy = self.startup_config.get('backend') == 'numpy'
        self.cancel_job = threading.Event()
        self.engine = None
        self.tracers = None
        self.phase = 'loading'
        self.mode = 'simulation'
        self.rate = 1.0
        self.attempts = 0
        self.challenge = None
        self.photo = None
        self._photo_options = None
        self.peak = 0.
        self.history = deque(maxlen=120)
        self.history_at = 0.
        self.timer = None
        self.last_clock = time.perf_counter()
        self.budget = 0.
        self.step_ms = 0.
        self.initial_config = {}
        self.review = False
        self.sequence = 0
        self.preparation_stage = ''

    @Slot()
    def start(self):
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.handle({'action':'setup', 'config':{'count':1024,'seed':735128,'impact':1.6,'speed':.9,**self.startup_config},'mode':'simulation'})

    def interrupted(self):
        return self.cancel_job.is_set() or QThread.currentThread().isInterruptionRequested()

    def emit_notice(self, text, busy=False, progress=0):
        self.message.emit({'type':'notice','text':text,'busy':busy,'progress':progress})

    def preparation_progress(self, text, fraction, start=0, span=100):
        if self.interrupted():
            raise PreparationCancelled()
        self.preparation_stage = text
        self.emit_notice(text, True, round(start + span*fraction))

    def make_engine(self, config, start=0, span=100):
        self.phase = 'loading'
        config = {'tracer_count':self.startup_config.get('tracer_count',15000),
                  **config, **({'backend':'numpy'} if self.force_numpy else {})}
        config['tracer_count'] = int(np.clip(int(config['tracer_count']), 0, 60000))
        return NBody(config, progress=lambda text, fraction:
                     self.preparation_progress(text, fraction, start, span))

    def make_tracers(self, engine):
        count = int(np.clip(int(engine.config.get('tracer_count', self.startup_config.get('tracer_count', 15000))), 0, 60000))
        if not count:
            return None
        self.preparation_stage = 'Preparing dense live stellar tracers'
        return DenseStars.from_engine(engine, count_per_galaxy=count)

    def snapshot(self):
        state = self.engine.snapshot()
        if self.tracers is not None:
            state['_tracers'] = self.tracers.snapshot()
        if self.photo is not None:
            state['_photo'] = self.photo.snapshot()
        return state

    def restore(self, state):
        # Validate the dense state before changing the massive engine.
        tracers = DenseStars.restore(state['_tracers']) if '_tracers' in state else self.make_tracers(self.engine)
        self.engine.restore(state)
        self.tracers = tracers
        if '_photo' in state:
            restored=PhotoHunt.restore(state['_photo'],self.engine,self.tracers)
            # Rewinding time does not refund used photography attempts.
            if self.photo is not None:
                restored.shot_count=self.photo.shot_count
                restored.best_score=self.photo.best_score
            restored.last_capture=None
            self.photo=restored

    def sync_tracers(self):
        if self.tracers is not None:
            delta = self.engine.time - self.tracers.time
            if delta > 1e-10:
                self.tracers.advance(self.engine, delta)

    def install_engine(self, engine, tracers=None):
        if tracers is None:
            tracers = self.make_tracers(engine)
        self.engine = engine
        self.tracers = tracers
        if self.mode=='photo':
            options=self._photo_options
            if options is None:
                options=(self.photo.objective,self.photo.round) if self.photo is not None else ('tidal',1)
            objective,round_number=options
            self.photo=PhotoHunt.from_scene(engine,tracers,objective,round_number)
        else:
            self.photo=None
        self._photo_options=None
        self.initial_config = dict(self.engine.config)
        self.phase = 'ready'
        self.review = False
        self.budget = 0.
        self.peak = 0.
        self.history.clear()
        self.history.append(self.snapshot())
        self.history_at = 0.
        self.last_clock = time.perf_counter()

    def build(self, config, start=0, span=100):
        engine = self.make_engine(config, start, span)
        self.install_engine(engine)
        self.emit_frame()

    def report_error(self, exc):
        details = traceback.format_exc()
        logging.getLogger(__name__).error('Physics operation failed at %s\n%s',
                                         self.preparation_stage, details)
        self.phase = 'paused' if self.engine is not None else 'error'
        if self.engine is not None:
            self.emit_frame()
        self.message.emit({'type':'error', 'text':f'{type(exc).__name__}: {exc}',
                           'stage':self.preparation_stage, 'details':details})

    @Slot(object)
    def handle(self, command):
        # Keep a working encounter intact if a replacement cannot be prepared.
        previous = (self.engine, self.mode, self.challenge, self.attempts, self.tracers, self.photo)
        self.preparation_stage = command.get('action', 'operation')
        try:
            action = command.get('action')
            if action == 'shape_setup':
                self.prepare_shape(command)
            elif action == 'photo_setup':
                self.prepare_photo(command.get('config',{}),command.get('objective','tidal'),1)
            elif action == 'photo_next':
                if self.mode=='photo' and self.photo is not None:
                    objective='bridge' if self.photo.objective=='tidal' else 'tidal'
                    round_number=2 if self.photo.round==1 else 1
                    self.prepare_photo(self.initial_config,objective,round_number)
            elif action == 'capture':
                self.capture_photo()
            elif action == 'setup':
                self.cancel_job.clear()
                self.mode = command.get('mode','simulation')
                self.attempts = 0
                self.challenge = None
                self.build(command['config'])
            elif action == 'apply':
                self.cancel_job.clear()
                if self.mode == 'game' and self.challenge:
                    cfg = {**self.initial_config, **command['config']}
                    # Preserve challenge's random seed and galaxy population.
                    for key in ['seed','count','massratio','inclination','isolated']:
                        cfg[key] = self.challenge['base'][key]
                    self.build(cfg)
                else:
                    self.build(command['config'])
            elif action == 'play':
                if self.engine is None: return
                if self.phase not in ('ready','running','paused','ended','review'): return
                if self.phase == 'running':
                    self.phase = 'paused'
                else:
                    if self.review or self.phase == 'ended' or self.engine.time >= END_TIME:
                        self.build(self.initial_config)
                    if self.phase == 'ready' and self.mode == 'game':
                        if self.attempts >= 3:
                            self.emit_notice('Three attempts used. Reset the challenge or choose New.'); return
                        self.attempts += 1
                    self.phase = 'running'
                    self.last_clock = time.perf_counter()
                    self.budget = 0.
                self.emit_frame()
            elif action == 'pause':
                if self.phase == 'running': self.phase = 'paused'
                self.emit_frame()
            elif action == 'reset':
                if self.attempts >= 3: self.attempts = 0
                if self.engine is not None: self.build(self.initial_config)
            elif action == 'rate':
                self.rate = float(np.clip(command['rate'], .25, 4.))
                self.budget = 0.
            elif action == 'rewind':
                if self.engine is None: return
                if self.mode == 'game' and self.phase not in ('ended','review'): return
                if len(self.history) <= 1:
                    self.emit_notice('No earlier history is available. Checkpoints store the current state; Reset returns to the beginning.'); return
                target = max(0., self.engine.time - 1.5)
                chosen = self.history[0]
                for state in self.history:
                    if state['ticks'] * self.engine.dt <= target: chosen = state
                self.restore(chosen)
                self.phase = 'review' if self.mode == 'game' else 'paused'
                self.review = self.mode == 'game'
                while self.history and self.history[-1]['ticks'] > chosen['ticks']: self.history.pop()
                self.history_at = self.engine.time
                self.budget = 0.
                self.emit_frame()
            elif action == 'challenge':
                self.prepare_challenge(command['config'])
            elif action == 'hint':
                if self.challenge:
                    if self.attempts >= 3: self.attempts = 0
                    self.build({**self.challenge['witness'],
                                'tracer_count':self.initial_config.get('tracer_count',15000)})
                    self.emit_notice('Helper setup loaded. Press Launch to watch a physically tested solution.')
            elif action == 'diagnostics':
                if self.engine is not None:
                    self.phase = 'paused' if self.phase == 'running' else self.phase
                    self.emit_frame()
                    e = self.engine.energy()
                    drift = abs((e-self.engine.initial_energy)/self.engine.initial_energy)
                    momentum = np.sum(self.engine.masses[:,None]*self.engine.velocities,axis=0)
                    self.message.emit({'type':'diagnostics','energy':e,'drift':drift,'momentum':float(np.linalg.norm(momentum)), 'angular':float(np.linalg.norm(self.engine.angularmomentum())), 'step_ms':self.step_ms,'backend':self.engine.backend,'particles':len(self.engine.masses)})
            elif action == 'save': self.save(command['path'])
            elif action == 'load': self.load(command['path'])
        except PreparationCancelled:
            self.engine, self.mode, self.challenge, self.attempts, self.tracers, self.photo = previous
            self._photo_options=None
            self.phase = 'paused' if self.engine is not None else 'error'
            if self.engine is not None: self.emit_frame()
            self.emit_notice('Preparation cancelled.')
        except Exception as exc:
            if self.engine is previous[0]:
                self.engine, self.mode, self.challenge, self.attempts, self.tracers, self.photo = previous
            self._photo_options=None
            self.report_error(exc)

    def prepare_shape(self,command):
        """Advance the same live solver to a suggested view, without altering paths."""
        shape=get_shape(command['shape_id'])
        self.cancel_job.clear()
        config=shape_config(command.get('config',{}),shape['id'])
        engine=self.make_engine(config,0,20)
        tracers=self.make_tracers(engine)
        preview=bool(command.get('preview',False))
        initial=engine.snapshot()
        if tracers is not None:initial['_tracers']=tracers.snapshot()
        if preview:
            steps=round(min(END_TIME,shape['time'])/engine.dt)
            for step in range(steps):
                if step%24==0:
                    self.preparation_progress('Evolving the encounter with live gravity',step/max(steps,1),20,78)
                engine.step()
                if tracers is not None:tracers.advance(engine,engine.dt)
        self.mode='simulation';self.challenge=None;self.attempts=0
        self.install_engine(engine,tracers)
        if preview:
            self.phase='paused';self.history.clear();self.history.append(initial)
            self.history.append(self.snapshot());self.history_at=engine.time
        self.emit_frame()
        self.emit_notice('Suggested moment ready. Play continues the live encounter; Reset returns to its beginning.'
                         if preview else 'Shape-inspired starting conditions ready. Press Play, or show the suggested moment.')

    def prepare_photo(self, requested, objective='tidal', round_number=1):
        if objective not in OBJECTIVES:raise ValueError('Unknown photo mission')
        self.cancel_job.clear()
        config={**requested,'seed':735128,'impact':1.6,'speed':.9,'massratio':1.,
                'inclination':25.,'spin':1,'isolated':False}
        self.emit_notice('Preparing a live stellar photography mission…',True,0)
        # Prepare a replacement completely before changing the active session.
        candidate=self.make_engine(config)
        tracers=self.make_tracers(candidate)
        photo=PhotoHunt.from_scene(candidate,tracers,objective,round_number)
        self.mode='photo';self.challenge=None;self.attempts=0
        self._photo_options=(objective,round_number)
        self.install_engine(candidate,tracers)
        self.photo=photo
        self.history.clear();self.history.append(self.snapshot())
        self.emit_frame();self.emit_notice('Photo mission ready. Start the encounter and capture the requested feature.')

    def capture_photo(self):
        if self.mode!='photo' or self.photo is None or self.engine is None:return
        if self.phase!='running':
            self.emit_notice('Start or resume the encounter before taking a photo.');return
        if self.photo.shot_count>=self.photo.max_shots:
            self.emit_notice('All three photos used. Retry the round or choose the next mission.');return
        self.sync_tracers()
        capture=self.photo.capture(self.engine,self.tracers)
        self.phase='ended' if self.photo.shot_count>=self.photo.max_shots else 'paused'
        self.budget=0.
        self.emit_frame()
        self.message.emit({'type':'photo_capture',**capture})

    def prepare_challenge(self, requested):
        self.phase = 'planning'
        self.cancel_job.clear()
        rng = np.random.default_rng(int(requested.get('seed',1)))
        cfg = {**requested, 'isolated':False,'massratio':float(rng.uniform(.85,1.2)), 'inclination':float(rng.uniform(5,35)), 'spin':1, 'impact':float(rng.uniform(1.5,2.)), 'speed':float(rng.uniform(.78,.95))}
        self.emit_notice('Preparing a solvable challenge with Python N-body physics…',True,0)
        witness = self.make_engine(cfg, 0, 15)
        peaks = {'tidal':0.,'bridge':0.}
        steps = math.ceil(END_TIME / witness.dt)
        done = 0
        while done < steps:
            if self.interrupted():
                raise PreparationCancelled()
            n = min(24,steps-done)
            witness.step(n); done += n
            m = witness.metrics()
            if m['after_pericentre'] and m['encounter']:
                for key in peaks: peaks[key] = max(peaks[key],m[key])
            self.preparation_progress(f'Testing challenge with live gravity: {done} / {steps} steps', done/steps, 15, 75)
        prefer_bridge = bool(rng.uniform() < .35)
        objective = 'bridge' if prefer_bridge and peaks['bridge'] > .01 else 'tidal'
        if peaks[objective] <= 0:
            raise RuntimeError('This encounter did not produce a reachable goal. Choose New to generate another.')
        self.challenge = {'objective':objective,'threshold':peaks[objective]*.58,'witness':dict(witness.config),'base':dict(witness.config)}
        self.mode = 'game'
        self.attempts = 0
        start = {**witness.config,'impact':float(rng.uniform(2.3,3.)), 'speed':float(rng.uniform(1.3,1.65))}
        self.build(start, 90, 10)
        self.emit_notice('Challenge ready. Change the approach, then launch.')

    @Slot()
    def tick(self):
        if self.engine is None or self.phase != 'running':
            self.last_clock = time.perf_counter(); return
        try:
            now = time.perf_counter()
            real_dt = min(.14, max(0.,now-self.last_clock))
            self.last_clock = now
            self.budget += real_dt*self.rate*1.1
            steps = min(8,int(self.budget/self.engine.dt))
            if steps < 1: return
            before = time.perf_counter()
            # Tracers observe the same sequence of fixed massive-body steps
            # at every playback rate, so visual rewind/replay is repeatable.
            if self.tracers is None:
                self.engine.step(steps)
            else:
                for _ in range(steps):
                    self.engine.step()
                    self.tracers.advance(self.engine, self.engine.dt)
            self.step_ms = (time.perf_counter()-before)*1000/steps
            self.budget = min(.15,max(0.,self.budget-steps*self.engine.dt))
            if self.engine.time-self.history_at >= .35:
                self.history.append(self.snapshot()); self.history_at=self.engine.time
            metrics = self.engine.metrics()
            if self.mode == 'game' and self.challenge:
                if metrics['after_pericentre'] and metrics['encounter']:
                    self.peak = max(self.peak,metrics[self.challenge['objective']])
                if self.peak >= self.challenge['threshold']:
                    self.finish(True); return
            if self.engine.time >= END_TIME:
                self.finish(False); return
            self.emit_frame(metrics)
        except Exception as exc:
            self.preparation_stage = 'Advancing live gravity'
            self.report_error(exc)

    def finish(self, success):
        self.phase = 'ended'
        self.review = self.mode == 'game'
        self.emit_frame()
        if self.mode == 'game':
            self.message.emit({'type':'result','success':success,'attempts':self.attempts,'objective':self.challenge['objective'],'score':max(1,min(3,4-self.attempts)) if success else 0})

    def emit_frame(self, metrics=None):
        if self.engine is None: return
        self.sync_tracers()
        self.sequence += 1
        frame = {'type':'frame','positions':self.engine.positions.astype(np.float32),'kind':self.engine.kind.copy(),'origin':self.engine.origin.copy(),'centers':self.engine.centers(), 'time':self.engine.time,'metrics':metrics or self.engine.metrics(),'config':dict(self.engine.config),'phase':self.phase,'mode':self.mode,'backend':self.engine.backend,'count':len(self.engine.masses),'attempts':self.attempts,'goal':self.challenge['objective'] if self.challenge else None,'progress':min(1.,self.peak/self.challenge['threshold']) if self.challenge else 0.,'step_ms':self.step_ms,'sequence':self.sequence}
        if self.photo is not None:frame['photo']=self.photo.summary()
        if self.tracers is not None:
            # Each frame owns its position buffer; Qt may consume it while the
            # worker advances the next step. Palette and origin are immutable.
            frame.update(tracer_positions=self.tracers.positions.astype(np.float32),
                         tracer_colors=self.tracers.colors,
                         tracer_origin=self.tracers.origin)
        self.message.emit(frame)

    def save(self,path):
        if self.engine is None: return
        if self.phase == 'running': self.phase = 'paused'
        self.sync_tracers()
        state = self.engine.snapshot()
        arrays = {k:v for k,v in state.items() if isinstance(v,np.ndarray)}
        meta = {k:v for k,v in state.items() if not isinstance(v,np.ndarray)}
        info = {'version':2,'config':self.engine.config,'state':meta,'mode':self.mode,'challenge':self.challenge,'attempts':self.attempts,'peak':self.peak,'phase':self.phase}
        if self.photo is not None:
            photo=self.photo.snapshot()
            arrays['photo_initial_radii']=photo.pop('initial_radii')
            info['photo']=photo
        if self.tracers is not None:
            dense = self.tracers.snapshot()
            info['tracers'] = {k:v for k,v in dense.items() if not isinstance(v,np.ndarray)}
            for key,value in dense.items():
                if isinstance(value,np.ndarray): arrays['tracer_'+key] = value
        arrays['metadata'] = np.array(json.dumps(info))
        with open(path,'wb') as output: np.savez_compressed(output,**arrays)
        self.emit_frame(); self.emit_notice('Checkpoint saved.'); self.message.emit({'type':'checkpoint','operation':'save','path':str(path)})

    def load(self,path):
        self.phase = 'paused'
        self.preparation_stage = 'Reading checkpoint'
        with np.load(path,allow_pickle=False) as data:
            info = json.loads(str(data['metadata'].item()))
            if info.get('version') not in (1,2): raise ValueError('Unsupported checkpoint version')
            cfg = info['config']
            if not 128 <= int(cfg['count']) <= 4096: raise ValueError('Invalid particle count')
            state = {**info['state'],**{k:data[k].copy() for k in ['positions','velocities','accelerations']}}
            dense_state = None
            photo_state = None
            if info.get('mode')=='photo' and not self.simulation_only:
                if not isinstance(info.get('photo'),dict) or 'photo_initial_radii' not in data.files:
                    raise ValueError('Photo checkpoint has no mission state')
                photo_state={**info['photo'],'initial_radii':data['photo_initial_radii'].copy()}
            if 'tracers' in info:
                if not isinstance(info['tracers'],dict): raise ValueError('Invalid dense stellar metadata')
                dense_state = {**info['tracers'], **{k[7:]:data[k].copy() for k in data.files if k.startswith('tracer_')}}
                if self.force_numpy: dense_state['accelerated'] = False
        candidate = self.make_engine(cfg)
        self.preparation_stage = 'Validating checkpoint state'
        candidate.restore(state)
        dense = DenseStars.restore(dense_state) if dense_state is not None else self.make_tracers(candidate)
        if dense is not None and abs(dense.time-candidate.time) > 1e-8:
            raise ValueError('Dense stellar time does not match checkpoint')
        # Old checkpoints keep their physical state, without restoring removed UI modes.
        mode = 'simulation' if self.simulation_only else info.get('mode','simulation')
        if mode not in ('simulation','game','andromeda','photo'): mode='simulation'
        photo=PhotoHunt.restore(photo_state,candidate,dense) if mode=='photo' else None
        challenge = info.get('challenge')
        attempts = 0 if self.simulation_only else int(np.clip(info.get('attempts',0),0,3))
        peak = 0. if self.simulation_only else float(info.get('peak',0.))
        if not math.isfinite(peak) or peak < 0: raise ValueError('Invalid challenge progress')
        if mode == 'game':
            if not isinstance(challenge, dict) or challenge.get('objective') not in ('tidal','bridge'):
                raise ValueError('Invalid game challenge')
            threshold = float(challenge.get('threshold',0))
            if not math.isfinite(threshold) or not 0 < threshold <= 1:
                raise ValueError('Invalid challenge target')
            for key in ('witness','base'):
                if not isinstance(challenge.get(key),dict) or not all(k in challenge[key] for k in ('seed','count','massratio','inclination','isolated')):
                    raise ValueError('Invalid challenge starting conditions')
        else:
            challenge = None
        self.install_engine(candidate, dense)
        self.mode, self.challenge, self.attempts, self.peak = mode, challenge, attempts, peak
        self.photo=photo
        saved_phase=info.get('phase','ready' if self.engine.ticks == 0 and self.attempts == 0 else 'paused')
        self.phase = saved_phase if saved_phase in ('ready','paused','ended','review') else 'paused'
        self.review = self.phase in ('ended','review')
        self.history.clear(); self.history.append(self.snapshot())
        self.history_at = self.engine.time
        self.emit_frame()
        notice = ('Checkpoint loaded. Dense stars regenerated for this older checkpoint.'
                  if dense_state is None and self.tracers is not None else 'Checkpoint loaded. Press Play to continue.')
        self.emit_notice(notice)
        self.message.emit({'type':'checkpoint','operation':'load','path':str(path)})
