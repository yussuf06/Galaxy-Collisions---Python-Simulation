from pathlib import Path
import re

source = Path(r'C:\Users\yusuf\Desktop\galaxy-python-desktop\galaxy-python-desktop')
target = Path(__file__).resolve().parent / 'free-simulation-ui'
(target / 'galaxy_app').mkdir(parents=True, exist_ok=True)
s = (source/'galaxy_app/window.py').read_text(encoding='utf-8')
def replace(old, new):
    global s
    assert old in s, old[:120]
    s = s.replace(old, new)
def remove_method(start, end):
    global s
    a=s.index('    def '+start); b=s.index('    def '+end,a)
    s=s[:a]+s[b:]

replace('from collections import deque\n','')
replace('QComboBox,QSlider,','QComboBox,QSlider,QDoubleSpinBox,')
replace('MODE_KEYS=["simulation","game","andromeda","photo"]\n','')
replace('"""Single native Qt application: 3-D Python simulation, game, and exhibit controls."""',
        '"""Native free galaxy simulation and exhibit controls."""')
replace('PhysicsWorker(startup_config)', "PhysicsWorker({**(startup_config or {}), 'simulation_only':True})")
replace("('Space',self.primary_action)","('Space',self.play)")
a=s.index('        mode_row='); b=s.index('        self.tabs=',a)
s=s[:a]+'''        mode_row=QHBoxLayout();self.mode_title=QLabel('المحاكاة الحرّة / Free simulation');self.mode_title.setStyleSheet('font-size:16px;font-weight:bold;');mode_row.addWidget(self.mode_title)
        self.mode_note=QLabel('Live 3D gravity · time and distances use model units.');self.mode_note.setWordWrap(True);self.mode_note.setStyleSheet('color:#97adc8;font-size:11px;');mode_row.addWidget(self.mode_note,1);outer.addLayout(mode_row)
'''+s[b:]
a=s.index('        self.goal_bar='); b=s.index('        self.resolution_group=',a)
s=s[:a]+s[b:]
replace("self.custom_settings=settings=QGroupBox('ضبط مخصّص / Custom conditions')", "self.custom_settings=settings=QGroupBox('شروط البداية / Starting conditions')")
a=s.index('        self.sliders={};self.outputs={}'); b=s.index('        self.spin=',a)
s=s[:a]+'''        self.sliders={};self.outputs={};self.value_inputs={};self.parameter_help={}
        parameters=[
            ('impact','Pass offset / انحراف المرور',-300,300,160,
             'معامل الإزاحة الجانبية عند البداية؛ 0 = بمحاذاة المركزين. الإشارة تحدّد جهة المرور، وليس أقل مسافة أثناء اللقاء.'),
            ('speed','Approach speed / سرعة الاقتراب',45,200,90,
             'معامل سرعة الاقتراب الابتدائية؛ قيمة أكبر = بداية أسرع. هذه قيمة نموذجية وليست كم/ث.'),
            ('massratio','Galaxy B mass / كتلة المجرّة ب',60,150,100,
             'كتلة ب ÷ كتلة أ؛ 1.00 = متساويتان، و0.65 = كتلة ب تساوي 65% من أ.'),
            ('inclination','Disk B tilt / ميل قرص ب',0,75,25,
             'ميل قرص ب بالدرجات بالنسبة لمستوى القرص المادي أ؛ 0° = مستويان متوازيان.')]
        for key,label,low,high,value,help_text in parameters:
            form.addWidget(QLabel(label))
            row=QHBoxLayout();number=QDoubleSpinBox();number.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            divisor=1 if key=='inclination' else 100
            number.setDecimals(0 if key=='inclination' else 2);number.setRange(low/divisor,high/divisor)
            number.setSingleStep(1 if key=='inclination' else .01);number.setValue(value/divisor)
            number.setSuffix('°' if key=='inclination' else ' ×' if key=='massratio' else '')
            number.setKeyboardTracking(False);number.setMinimumWidth(92);number.setMaximumWidth(110)
            number.setAccessibleName(label);number.setToolTip(help_text);row.addWidget(number)
            out=QLabel();out.setWordWrap(True);out.setStyleSheet('color:#a5d9ff;font-size:11px;');row.addWidget(out,1,Qt.AlignmentFlag.AlignRight);form.addLayout(row)
            slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(low,high);slider.setValue(value)
            slider.setToolTip(help_text);slider.setAccessibleName(label)
            slider.valueChanged.connect(self.mark_dirty);number.valueChanged.connect(lambda v,control=slider,d=divisor:control.setValue(round(v*d)))
            form.addWidget(slider)
            help_label=QLabel(help_text);help_label.setWordWrap(True);help_label.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            help_label.setStyleSheet('color:#98adc6;font-size:11px;font-weight:normal;');form.addWidget(help_label)
            self.sliders[key]=slider;self.outputs[key]=out;self.value_inputs[key]=number;self.parameter_help[key]=help_label
            self.physical_controls.extend([slider,number])
'''+s[b:]
replace('        self.build_photo_controls(p)\n','')
replace("'Reset / retry'","'Reset'")
replace("row.addWidget(self.rewind_button);self.helper_button=QPushButton('Helper setup');self.helper_button.clicked.connect(lambda:self.send('hint'));row.addWidget(self.helper_button);p.addLayout(row);self.controls.extend([self.rewind_button,self.helper_button])", "row.addWidget(self.rewind_button);p.addLayout(row);self.controls.append(self.rewind_button)")
replace(',self.helper_button','')
replace('        column.addWidget(self.photo_button);column.addWidget(self.photo_next_button);column.addWidget(self.play_button)', '        column.addWidget(self.play_button)')
replace('pinned.addWidget(self.rewind_button);pinned.addWidget(self.helper_button);column.addLayout(pinned)', 'pinned.addWidget(self.rewind_button);column.addLayout(pinned)')
replace("[('Original main.py style','cinematic'),('Original style · lighter draw','balanced'),('Raw gravity particles','raw')]", "[('Original main.py style','cinematic')]")
replace('Reference spiral stars move in the live galaxy gravity field. Raw shows the massive solver particles; Resolution sets their count.', 'Original reference spiral stars moving in the live gravity field.')
replace("'أنماط اللقاء / Encounter modes'", "'إعدادات جاهزة / Presets'")
replace("self.custom_settings.setVisible(self.mode!='photo' and (ident=='custom' or self.mode=='game'))", 'self.custom_settings.show()')
replace("self.custom_settings.setVisible(self.mode!='photo')", 'self.custom_settings.show()')
replace("        if self.mode=='andromeda':config['isolated']=False\n",'')
remove_method('build_photo_controls(', 'toggle_cinema(')
# Remove references to the retired modes from presenter text too.
replace('بينما تبقى جسيمات العينة المادية والنجوم والمادة المظلمة متجاذبة وتحسب منها أهداف اللعبة.', 'بينما تبقى جسيمات العينة المادية من نجوم ومادة مظلمة متجاذبة.')
replace('، واختيار Raw gravity particles لفحص العينة المادية','')
replace('غيّر طريقة اللقاء وحاول تحقّق هدف الجولة.', 'غيّر عاملًا واحدًا من شروط البداية وقارن حركة النجوم.')
a=s.index('<h2>درب التبانة وأندروميدا</h2>'); b=s.index('<h2>ملاحظات للمقدّم</h2>',a);s=s[:a]+s[b:]
s=re.sub(r' · <a href="https://arxiv.org/abs/2603\.22863">.*?</a>', '', s)
a=s.index('    def update_labels('); b=s.index('    def mark_dirty(',a)
s=s[:a]+'''    def update_labels(self):
        raw={key:control.value() for key,control in self.sliders.items()}
        for key,value in raw.items():
            number=self.value_inputs[key];blocker=QSignalBlocker(number)
            number.setValue(value if key=='inclination' else value/100);del blocker
        impact=abs(raw['impact']);speed=raw['speed'];mass=raw['massratio'];tilt=raw['inclination']
        self.outputs['impact'].setText('قريب من المواجهة' if impact<40 else 'مرور واسع' if impact>230 else 'مرور جانبي')
        self.outputs['speed'].setText('بطيء نسبيًا' if speed<85 else 'سريع' if speed>135 else 'متوسط')
        self.outputs['massratio'].setText('كتلة متساوية' if mass==100 else f"ب = {mass}% من كتلة أ")
        self.outputs['inclination'].setText('مستويان متوازيان' if tilt==0 else 'ميل كبير' if tilt>50 else 'قرص مائل')

'''+s[b:]
replace("        if self._photo_replay is not None:self.stop_photo_replay()\n",'')
replace("('reset','hint','load','photo_next')", "('reset','load')")
replace('        self.mode_combo.setEnabled(not value)\n','')
replace("'photo_setup' if self.mode=='photo' else 'challenge' if self.mode=='game' else 'setup'", "'setup'")
a=s.index('    def update_control_state(');b=s.index('    def apply(',a)
s=s[:a]+'''    def update_control_state(self):
        running=bool(self.frame and self.frame['phase']=='running')
        for widget in self.physical_controls:widget.setEnabled(not self.busy and not running)
        self.rewind_button.setEnabled(not self.busy and bool(self.frame))

'''+s[b:]
remove_method('change_mode(', 'new(')
replace("        if self.mode not in ('game','photo'):\n            self.sliders", "        if self.mode=='simulation':\n            self.sliders")
a=s.index("        if kind=='photo_capture':");b=s.index("        if kind=='checkpoint':",a);s=s[:a]+s[b:]
a=s.index("        if kind=='result':");b=s.index("        if kind!='frame':return",a);s=s[:a]+s[b:]
a=s.index("        if msg['mode']=='photo':");b=s.index('        self.frame=msg;',a);s=s[:a]+s[b:]
replace("        if self.mode!='photo' or msg['phase']=='running':self.view.set_photo_evidence(None)\n",'')
replace("                self.goal_bar.setValue(round(msg['progress']*100))\n",'')
replace("'راقب المشهد — Space يلتقط الصورة' if self.mode=='photo' else ", '')
replace('        blocker=QSignalBlocker(self.mode_combo);self.mode_combo.setCurrentIndex(MODE_KEYS.index(self.mode));del blocker\n','')
a=s.index("        self.goal_bar.setVisible(");b=s.index('        self.status.setText(',a)
s=s[:a]+'''        self.goal_title.setText('Explore live self-gravity')
        self.goal_copy.setText('Adjust the numbers below, apply, then compare. Change one starting condition at a time.')
        self.mode_note.setText('Free simulation · values use model units; playback changes viewing speed only.')
'''+s[b:]
replace('        self.update_photo_ui(msg)\n','')
replace('        self.photo_replay_timer.stop()\n','')
# Ensure no retired UI object or path survived.
assert not any(token in s for token in ('self.photo_', 'self.helper_button', 'self.goal_bar', 'mode_combo', 'MODE_KEYS'))
(target/'galaxy_app/window.py').write_text(s,encoding='utf-8')

w=(source/'galaxy_app/worker.py').read_text(encoding='utf-8')
w=w.replace("        self.force_numpy =", "        self.simulation_only = bool(self.startup_config.pop('simulation_only', False))\n        self.force_numpy =",1)
w=w.replace("            if info.get('mode')=='photo':", "            if info.get('mode')=='photo' and not self.simulation_only:")
w=w.replace("        mode = info.get('mode','simulation')", "        # Old checkpoints keep their physical state, without restoring removed UI modes.\n        mode = 'simulation' if self.simulation_only else info.get('mode','simulation')")
w=w.replace("        attempts = int(np.clip(info.get('attempts',0),0,3))", "        attempts = 0 if self.simulation_only else int(np.clip(info.get('attempts',0),0,3))")
w=w.replace("        peak = float(info.get('peak',0.))", "        peak = 0. if self.simulation_only else float(info.get('peak',0.))")
(target/'galaxy_app/worker.py').write_text(w,encoding='utf-8')

smoke=(source/'galaxy_app/smoke_test.py').read_text(encoding='utf-8')
a=smoke.index('        w.mode_combo.setCurrentIndex(2)');b=smoke.index('        # Snapshot actual Qt widgets',a)
smoke=smoke[:a]+'''        assert w.mode=='simulation' and not hasattr(w,'mode_combo')
        assert w.custom_settings.isVisible()
        assert w.display_style.count()==1 and w.display_style.currentData()=='cinematic'
        w.value_inputs['speed'].setValue(.65);w.value_inputs['massratio'].setValue(1.2)
        assert w.configuration()['speed']==.65 and w.sliders['massratio'].value()==120
        assert '120%' in w.outputs['massratio'].text()
        w.encounter_combo.setCurrentIndex(w.encounter_combo.findData('slowclose'))
        assert w.custom_settings.isVisible() and w.value_inputs['impact'].value()==.65
        w.apply_button.click();wait(lambda:not w.busy and w.frame['config']['speed']==.65)
        w.halos.setChecked(True);w.camera_preset('front');app.processEvents();w.camera_preset('reset')
'''+smoke[b:]
smoke=smoke.replace("w.play_button.click();wait(lambda:w.frame['phase']=='running');assert w.frame['attempts']==2 and w.frame['progress']==0", "w.play_button.click();wait(lambda:w.frame['phase']=='running');assert w.frame['mode']=='simulation'")
smoke=smoke.replace('Andromeda, game-ready checkpoint attempts, physically solvable helper, new random challenge', 'numeric inputs, always-visible starting conditions, original style only, new random encounter')
(target/'galaxy_app/smoke_test.py').write_text(smoke,encoding='utf-8')
print('Prepared window.py, worker.py and smoke_test.py in', target)
