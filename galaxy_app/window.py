"""Native free galaxy simulation and exhibit controls."""
from __future__ import annotations
import math, secrets, json, time
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QTimer,QThread,Signal,Slot,QPointF,QRectF,QSignalBlocker
from PySide6.QtGui import QPainter,QColor,QPen,QRadialGradient,QPixmap,QFont,QFontDatabase,QKeySequence,QShortcut
from PySide6.QtWidgets import (QMainWindow,QWidget,QApplication,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QComboBox,QSlider,QDoubleSpinBox,QCheckBox,QGroupBox,QScrollArea,QTabWidget,QTextBrowser,QProgressBar,QFileDialog,QMessageBox,QSplitter)
from .worker import PhysicsWorker, END_TIME
from .encounters import PRESETS, get_preset, match_config
from .shape_presets import SHAPES,get_shape
from .colour import PALETTES
from .reference_shapes import reference_frame


STYLE='''
QMainWindow,QWidget{background:#090e1b;color:#eaf1ff;font-family:Arial;font-size:12px;}
QGroupBox{border:1px solid #2d3c56;border-radius:10px;margin-top:12px;padding:12px;font-weight:bold;}
QGroupBox::title{subcontrol-origin:margin;left:13px;padding:0 5px;color:#b6c8e2;}
QPushButton{background:#18253c;border:1px solid #354764;border-radius:7px;padding:9px 11px;}
QPushButton:hover{background:#283d58;border-color:#7dacc9;}
QPushButton:checked{background:#285765;border-color:#8adbe7;color:#efffff;}
QPushButton:disabled{color:#697588;border-color:#26334a;background:#111a2a;}
QPushButton#primary{background:#ffbba4;color:#33232a;font-weight:bold;border:0;padding:13px;}
QPushButton#primary:hover{background:#ffdbc9;}
QComboBox{background:#111d30;border:1px solid #35445e;border-radius:6px;padding:7px;min-height:18px;}
QComboBox QAbstractItemView{background:#142139;selection-background-color:#355176;}
QDoubleSpinBox{background:#111d30;border:1px solid #557393;border-radius:5px;padding:5px;color:#d1efff;font-size:13px;}
QSlider::groove:horizontal{height:4px;background:#2b3b56;border-radius:2px;}
QSlider::handle:horizontal{background:#a6dcff;border:1px solid #d4eaff;width:14px;margin:-6px 0;border-radius:7px;}
QProgressBar{border:1px solid #34445e;border-radius:5px;background:#0e192b;text-align:center;min-height:14px;font-size:10px;}
QProgressBar::chunk{background:#78abca;border-radius:4px;}
QCheckBox{spacing:7px;color:#b5c7de;}
QCheckBox::indicator{width:15px;height:15px;}
QTextBrowser{border:1px solid #2c3e59;border-radius:10px;padding:12px;background:#101a2d;font-size:14px;}
QTabWidget::pane{border:0;}
QTabBar::tab{background:#111c30;color:#9bb0cc;padding:10px 20px;border-bottom:2px solid #1c2d44;}
QTabBar::tab:selected{color:#d7edff;border-bottom:2px solid #a3d9ff;}
QScrollArea{border:0;}
QToolTip{background:#233b54;color:white;border:1px solid #6f93b2;padding:5px;}
'''

from .rendering import GalaxyView

class MainWindow(QMainWindow):
    command=Signal(object)
    def __init__(self,startup_config=None):
        super().__init__()
        # Windows' offscreen Qt plugin may not enumerate any system fonts.
        # Load the existing local fonts for readable render verification.
        if not QFontDatabase.families():
            for font in ('C:/Windows/Fonts/segoeui.ttf','C:/Windows/Fonts/arial.ttf','C:/Windows/Fonts/tahoma.ttf'):
                if Path(font).is_file():QFontDatabase.addApplicationFont(font)
        self.setWindowTitle('لقاء المجرّات — Galaxy Encounter / Free simulation')
        self.resize(1320,860);self.setMinimumSize(980,700);self.setStyleSheet(STYLE)
        self.frame=None;self.mode='simulation';self.seed=735128;self.busy=True;self.dirty=False;self.closing=False
        self.busy_since=time.monotonic();self.stage_since=self.busy_since;self.stage_text='';self.last_error=None
        self.controls=[];self.physical_controls=[]
        self.extra_config={'aligned_disks':False,'shape_id':''}
        self._active_shape_id=None;self._pending_shape_id=None
        self.illustration_id=None;self._saved_view=None
        self.build_ui()
        self.thread=QThread(self);self.worker=PhysicsWorker({**(startup_config or {}), 'simulation_only':True});self.worker.moveToThread(self.thread)
        self.command.connect(self.worker.handle);self.worker.message.connect(self.on_message)
        self.thread.started.connect(self.worker.start);self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()
        for key,callback in [('Space',self.play),('R',lambda:self.send('reset')),('N',self.new),('F',self.fullscreen),('C',self.toggle_cinema),('Esc',self.exit_fullscreen)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(callback)
        self.render_timer=QTimer(self);self.render_timer.setTimerType(Qt.TimerType.PreciseTimer);self.render_timer.setInterval(16 if hasattr(self.view,"canvas") else 80);self.render_timer.timeout.connect(self.view.animate);self.render_timer.start()
        self.preparation_timer=QTimer(self);self.preparation_timer.setInterval(1000);self.preparation_timer.timeout.connect(self.refresh_preparation);self.preparation_timer.start()
        self.set_busy(True,'Preparing the Python N-body engine…')

    def build_ui(self):
        root=QWidget();self.setCentralWidget(root);outer=QVBoxLayout(root);outer.setContentsMargins(20,16,20,12);outer.setSpacing(12)
        top=QHBoxLayout();title=QLabel('لقاء المجرّات');title.setStyleSheet('font-size:30px;font-weight:bold;color:#ffd0ba;');top.addWidget(title)
        subtitle=QLabel('PYTHON / LIVE 3D SELF-GRAVITY');subtitle.setStyleSheet('color:#9ac9ed;font-size:10px;letter-spacing:2px;');top.addWidget(subtitle);top.addStretch()
        for text,callback in [('Cinema (C)',self.toggle_cinema),('Save PNG',self.screenshot),('Save checkpoint',self.save_checkpoint),('Load checkpoint',self.load_checkpoint),('Fullscreen',self.fullscreen)]:
            b=QPushButton(text);b.clicked.connect(callback);top.addWidget(b);self.controls.append(b)
            if text=='Save checkpoint':self.save_checkpoint_button=b
        outer.addLayout(top)
        mode_row=QHBoxLayout();self.mode_title=QLabel('المحاكاة الحرّة / Free simulation');self.mode_title.setStyleSheet('font-size:16px;font-weight:bold;');mode_row.addWidget(self.mode_title)
        self.mode_note=QLabel('Live 3D gravity · time and distances use model units.');self.mode_note.setWordWrap(True);self.mode_note.setStyleSheet('color:#97adc8;font-size:11px;');mode_row.addWidget(self.mode_note,1);outer.addLayout(mode_row)
        self.tabs=QTabWidget();outer.addWidget(self.tabs,1)
        universe=QWidget();u=QHBoxLayout(universe);u.setContentsMargins(0,9,0,0);u.setSpacing(14)
        left=QVBoxLayout();self.view=GalaxyView();left.addWidget(self.view,1)
        self.camera_bar=QWidget();camera=QHBoxLayout(self.camera_bar);camera.setContentsMargins(0,0,0,0)
        for text,callback in [('Top view',lambda:self.camera_preset('top')),('Front view',lambda:self.camera_preset('front')),('Oblique',lambda:self.camera_preset('oblique')),('Reset view',lambda:self.camera_preset('reset')),('−',lambda:self.zoom(.8)),('+',lambda:self.zoom(1.25))]:
            b=QPushButton(text);b.clicked.connect(callback);camera.addWidget(b)
        self.auto=QPushButton('Tracking camera');self.auto.setCheckable(True);self.auto.setChecked(self.view.auto);self.auto.toggled.connect(self.view.set_tracking);self.view.auto_changed.connect(self.auto.setChecked);self.auto.setToolTip('Follow both galaxies and automatically zoom out for spreading stars, or in as they come together. Right-drag to leave tracking; Reset view restores the reference camera.');camera.addWidget(self.auto)
        self.halos=QCheckBox('Dark matter');self.halos.toggled.connect(lambda v:setattr(self.view,'halos',v));camera.addWidget(self.halos);left.addWidget(self.camera_bar)
        self.time_bar=QProgressBar();self.time_bar.setRange(0,1000);self.time_bar.setFormat('Encounter timeline — model units');left.addWidget(self.time_bar);u.addLayout(left,1)
        panel=QWidget();panel.setFixedWidth(325);p=QVBoxLayout(panel);p.setContentsMargins(2,0,7,0);p.setSpacing(11)
        self.goal_title=QLabel('Prepare an encounter');self.goal_title.setStyleSheet('font-size:18px;font-weight:bold;color:#ffccb5;');p.addWidget(self.goal_title)
        self.goal_copy=QLabel('Change a starting condition, apply it, then compare the stellar motion.');self.goal_copy.setWordWrap(True);self.goal_copy.setStyleSheet('color:#9db1cc;font-size:11px;');p.addWidget(self.goal_copy)
        self.build_shape_controls(p)
        self.resolution_group=QGroupBox('الدقّة / Resolution');qform=QVBoxLayout(self.resolution_group)
        quality_row=QHBoxLayout();quality_row.addWidget(QLabel('Gravity resolution'));self.quality=QComboBox()
        for label,count in [('Fast · 512',512),('Balanced · 1,024',1024),('High · 2,048',2048)]:self.quality.addItem(label,count)
        self.quality.setCurrentIndex(1);self.quality.currentIndexChanged.connect(self.mark_dirty);quality_row.addWidget(self.quality,1);qform.addLayout(quality_row);self.physical_controls.append(self.quality)
        star_row=QHBoxLayout();star_row.addWidget(QLabel('Stars / galaxy'));self.star_density=QComboBox()
        for count in (3000,7500,15000,30000):self.star_density.addItem(f'{count:,}',count)
        self.star_density.setCurrentIndex(2);self.star_density.currentIndexChanged.connect(self.mark_dirty);star_row.addWidget(self.star_density,1);qform.addLayout(star_row);self.physical_controls.append(self.star_density)
        self.star_density.setToolTip('Applies with new starting conditions. These visible stars are tracers of the live gravity field.')
        self.build_encounter_controls(p)
        self.custom_settings=settings=QGroupBox('شروط البداية / Starting conditions');form=QVBoxLayout(settings);form.setSpacing(6)
        self.sliders={};self.outputs={};self.value_inputs={};self.parameter_help={}
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
        form.addWidget(QLabel('Galaxy B / شكل المجرّة ب'))
        self.morphology_b=QComboBox();self.morphology_b.addItem('Spiral / حلزونية','spiral');self.morphology_b.addItem('Round spheroid / كروية','spheroid');self.morphology_b.currentIndexChanged.connect(self.mark_dirty);form.addWidget(self.morphology_b);self.physical_controls.append(self.morphology_b)
        self.spin=QComboBox();self.spin.addItems(['Rotate in same direction','Rotate in opposite direction']);self.spin.currentIndexChanged.connect(self.mark_dirty);form.addWidget(self.spin);self.physical_controls.append(self.spin)
        self.isolate=QCheckBox('Isolated galaxy — control experiment');self.isolate.toggled.connect(self.mark_dirty);form.addWidget(self.isolate);self.physical_controls.append(self.isolate)
        self.apply_button=QPushButton('Apply new starting conditions');self.apply_button.clicked.connect(self.apply);self.physical_controls.append(self.apply_button);p.addWidget(settings);p.addWidget(self.apply_button);p.addWidget(self.resolution_group);self.build_appearance_controls(p)
        self.play_button=QPushButton('Preparing…');self.play_button.setObjectName('primary');self.play_button.clicked.connect(self.play);p.addWidget(self.play_button);self.controls.append(self.play_button)
        row=QHBoxLayout();self.reset_button=QPushButton('Reset');self.reset_button.clicked.connect(lambda:self.send('reset'));row.addWidget(self.reset_button);self.new_button=QPushButton('New random');self.new_button.clicked.connect(self.new);row.addWidget(self.new_button);p.addLayout(row);self.controls.extend([self.reset_button,self.new_button])
        row=QHBoxLayout();self.rewind_button=QPushButton('Rewind');self.rewind_button.clicked.connect(lambda:self.send('rewind'));row.addWidget(self.rewind_button);p.addLayout(row);self.controls.append(self.rewind_button)
        row=QHBoxLayout();self.rate=QComboBox()
        for name,v in [('½×',.5),('1×',1.),('2×',2.),('4×',4.)]:self.rate.addItem(name,v)
        self.rate.setCurrentIndex(1);self.rate.currentIndexChanged.connect(lambda:self.command.emit({'action':'rate','rate':self.rate.currentData()}));row.addWidget(self.rate,1);p.addLayout(row)
        self.diagnostic_button=diagnostic=QPushButton('Physics diagnostics / accuracy');diagnostic.clicked.connect(lambda:self.send('diagnostics'));p.addWidget(diagnostic);self.controls.append(diagnostic)
        self.physics_note=QLabel('All sampled stars and halo particles attract one another. No imposed galaxy paths or forced mergers.');self.physics_note.setWordWrap(True);self.physics_note.setStyleSheet('color:#839ab6;font-size:10px;');p.addWidget(self.physics_note);p.addStretch()
        scroll=QScrollArea();scroll.setWidget(panel);scroll.setWidgetResizable(True)
        # Keep booth controls pinned while advanced parameters can scroll.
        self.side=side=QWidget();side.setFixedWidth(345);column=QVBoxLayout(side);column.setContentsMargins(0,0,0,0);column.setSpacing(8);column.addWidget(scroll,1)
        def detach(layout,widget):
            for i in range(layout.count()):
                item=layout.itemAt(i)
                if item.widget() is widget:layout.removeWidget(widget);return True
                if item.layout() and detach(item.layout(),widget):return True
            return False
        for widget in [self.play_button,self.reset_button,self.new_button,self.rewind_button,self.rate]:detach(p,widget)
        column.addWidget(self.play_button)
        pinned=QHBoxLayout();pinned.addWidget(self.reset_button);pinned.addWidget(self.new_button);column.addLayout(pinned)
        pinned=QHBoxLayout();pinned.addWidget(self.rewind_button);column.addLayout(pinned)
        pinned=QHBoxLayout();self.rate_label=QLabel('سرعة المشاهدة');pinned.addWidget(self.rate_label);pinned.addWidget(self.rate,1);column.addLayout(pinned)
        u.addWidget(side);self.tabs.addTab(universe,'3D encounter')
        notes=QTextBrowser();notes.setOpenExternalLinks(True);notes.setHtml(self.presenter_html().replace('</html>',self.presenter_gpu_note()+'</html>'));self.tabs.addTab(notes,'الشرح العربي / Presenter guide')
        self.error_label=QLabel();self.error_label.setWordWrap(True);self.error_label.setTextFormat(Qt.TextFormat.PlainText);self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);self.error_label.setStyleSheet('color:#ffd0ba;background:#392332;padding:8px;');self.error_label.hide();outer.addWidget(self.error_label)
        bottom=QHBoxLayout();self.status=QLabel('Loading…');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);self.status.setStyleSheet('color:#9fb8d1;');bottom.addWidget(self.status,1);self.busy_bar=QProgressBar();self.busy_bar.setRange(0,100);self.busy_bar.setMaximumWidth(230);self.busy_bar.setFormat('Preparation %p%');bottom.addWidget(self.busy_bar);outer.addLayout(bottom)
        keys=QLabel('Space play/pause · R reset · N new · F fullscreen · Left-drag rotate · Right-drag pan · Wheel zoom');keys.setStyleSheet('color:#6f87a6;font-size:10px;');outer.addWidget(keys);self.update_labels()

    def build_appearance_controls(self, layout):
        group=QGroupBox('Appearance / live view'); form=QVBoxLayout(group)
        self.display_style=QComboBox()
        for label,value in [('Original main.py style','cinematic')]:
            self.display_style.addItem(label,value)
        self.display_style.currentIndexChanged.connect(lambda:self.view.set_detail(self.display_style.currentData()))
        self.display_style.setToolTip('Original reference spiral stars moving in the live gravity field.')
        form.addWidget(self.display_style)
        self.palette_combo=QComboBox()
        for ident,palette in PALETTES.items():self.palette_combo.addItem(palette[0],ident)
        self.palette_combo.currentIndexChanged.connect(lambda:self.view.set_palette(self.palette_combo.currentData()))
        self.palette_label=QLabel('Colour palette / الألوان');form.addWidget(self.palette_label);form.addWidget(self.palette_combo)
        self.highlight_protection=QCheckBox('Preserve colour in bright cores');self.highlight_protection.setChecked(True)
        self.highlight_protection.toggled.connect(lambda value:(setattr(self.view,'protect_highlights',value),self.view.update()))
        form.addWidget(self.highlight_protection)
        self.appearance_sliders={};self.appearance_rows={}
        for key,label,low,high,value in [('exposure','Brightness',15,250,125),('star_size','Star size',40,230,100),('core_detail','Core detail',50,200,100)]:
            row=QHBoxLayout();caption=QLabel(label);row.addWidget(caption); output=QLabel('1.00×'); row.addWidget(output,1,Qt.AlignmentFlag.AlignRight); form.addLayout(row)
            slider=QSlider(Qt.Orientation.Horizontal); slider.setRange(low,high); slider.setValue(value)
            def adjust(v,k=key,out=output):
                setattr(self.view,k,v/100);out.setText(f'{v/100:.2f}×');self.view.update()
            slider.valueChanged.connect(adjust);adjust(value);form.addWidget(slider);self.appearance_sliders[key]=slider
            self.appearance_rows[key]=(caption,output,slider)
        row=QHBoxLayout()
        self.orbit=QCheckBox('Orbit camera');self.orbit.toggled.connect(lambda v:setattr(self.view,'orbit',v));self.view.orbit_changed.connect(self.orbit.setChecked);row.addWidget(self.orbit)
        self.orbit.toggled.connect(self.update_illustration_play)
        self.labels=QCheckBox('Labels');self.labels.setChecked(self.view.labels);self.labels.toggled.connect(lambda v:setattr(self.view,'labels',v));row.addWidget(self.labels);form.addLayout(row)
        row=QHBoxLayout()
        self.trails=QCheckBox('Center trails');self.trails.toggled.connect(lambda v:setattr(self.view,'tracks',v));row.addWidget(self.trails)
        self.starfield=QCheckBox('Background stars');self.starfield.setChecked(True);self.starfield.toggled.connect(lambda v:setattr(self.view,'background',v));row.addWidget(self.starfield);form.addLayout(row)
        self.render_stats=QCheckBox('Show rendering stats');self.render_stats.toggled.connect(lambda v:setattr(self.view,'stats',v));form.addWidget(self.render_stats)
        self.appearance_hint=hint=QLabel('Colours are illustrative. Bright-core protection keeps the stellar structure visible.');hint.setWordWrap(True);hint.setStyleSheet('color:#839ab6;font-size:10px;');form.addWidget(hint)
        self.appearance_group=group;layout.addWidget(group)

    def build_shape_controls(self,layout):
        group=QGroupBox('أشكال من الصور / Photo illustrations');box=QVBoxLayout(group)
        grid=QGridLayout();self.shape_buttons={}
        for index,shape in enumerate(SHAPES):
            button=QPushButton(shape['name']);button.setCheckable(True)
            button.clicked.connect(lambda checked=False,ident=shape['id']:self.show_reference_shape(ident))
            grid.addWidget(button,index//2,index%2);self.shape_buttons[shape['id']]=button;self.controls.append(button)
        box.addLayout(grid)
        self.shape_description=QLabel('Photo-derived particle illustrations. Separate from the live gravity simulation.');self.shape_description.setWordWrap(True);self.shape_description.setStyleSheet('color:#a5bcd4;font-size:11px;');box.addWidget(self.shape_description)
        self.shape_description.setOpenExternalLinks(True)
        self.shape_preview_button=QPushButton('المحاكاة الحرة / Back to gravity')
        self.shape_preview_button.clicked.connect(self.leave_illustration)
        self.shape_preview_button.hide();self.controls.append(self.shape_preview_button);box.addWidget(self.shape_preview_button)
        # Legacy illustration handlers remain available without an exhibit panel.
        self.shape_group=group
        group.hide()
        layout.addWidget(group)

    def show_reference_shape(self,ident):
        if self.busy:return
        frame=reference_frame(ident)
        if self.illustration_id is None:
            keys=('yaw','pitch','zoom','pan','center','extent','auto','orbit','labels','halos','tracks','exposure','star_size','core_detail','protect_highlights')
            self._saved_view={key:(getattr(self.view,key).copy() if isinstance(getattr(self.view,key),np.ndarray) else getattr(self.view,key)) for key in keys}
            if hasattr(self.view,'_manual_distance'):self._saved_view['_manual_distance']=self.view._manual_distance
        self.illustration_id=ident;self._pending_shape_id=None
        self.command.emit({'action':'pause'})
        self.view.set_data(frame)
        for checkbox in (self.orbit,self.labels,self.trails,self.halos):checkbox.setChecked(False)
        self.highlight_protection.setChecked(True)
        self.appearance_sliders['exposure'].setValue(165);self.appearance_sliders['star_size'].setValue(70)
        self.reference_camera()
        info=frame['illustration']
        self.mode_title.setText('عرض توضيحي من الصورة / Photo illustration')
        self.mode_note.setText('Particles sampled from the reference photo. Depth is illustrative; no gravity evolution.')
        self.goal_title.setText(info['title']);self.goal_copy.setText('Zoom or drag to inspect. Rotate view moves the camera only. Reset restores the photo angle.')
        self.shape_description.setText(' + '.join(info['names'])+'<br>'+info['credit']+f'<br><a style="color:#a6dcff" href="{info["source"]}">Reference photo / المصدر</a>')
        self.status.setText(f"ILLUSTRATION · {frame['count']:,} photo samples · synthetic depth · gravity simulation paused")
        self.set_illustration_controls(True);self.update_illustration_play();self.update_control_state();self.view.update()

    def set_illustration_controls(self,active):
        for widget in (self.encounter_group,self.custom_settings,self.resolution_group,self.apply_button,self.new_button,self.rewind_button,self.rate,self.rate_label,self.time_bar,self.diagnostic_button,self.physics_note):
            widget.setVisible(not active)
        self.shape_preview_button.setVisible(active)
        for widget in (self.palette_combo,self.display_style,self.appearance_sliders['core_detail'],self.auto,self.halos,self.trails):widget.setEnabled(not active)
        for widget in (self.palette_combo,self.palette_label,self.display_style,self.auto,self.halos,self.trails,*self.appearance_rows['core_detail']):widget.setVisible(not active)
        self.appearance_hint.setText('Reference-photo colours. Brightness and point size affect only this illustration.' if active else 'Colours are illustrative. Bright-core protection keeps the stellar structure visible.')
        self.save_checkpoint_button.setEnabled(not active and not self.busy)
        self.reset_button.setText('Reset photo angle' if active else 'Reset')

    def reference_camera(self):
        self.orbit.setChecked(False);self.auto.setChecked(False);self.view.reset_camera();self.view.set_tracking(False)
        self.view.yaw=0.;self.view.pitch=0.;self.view.zoom=1.;self.view.pan[:]=0.;self.view.center[:]=0.
        points=self.view.data['positions'];radius=float(np.quantile(np.linalg.norm(points,axis=1),.995))
        if hasattr(self.view,'_manual_distance'):self.view._manual_distance=radius/math.sin(math.radians(22.5))*1.08
        else:self.view.extent=radius*1.08
        self.view.update()

    def update_illustration_play(self,*args):
        if self.illustration_id:self.play_button.setText('Pause rotation Ⅱ' if self.orbit.isChecked() else 'Rotate view / تدوير العرض')

    def leave_illustration(self):
        if self.illustration_id is None:return
        self.illustration_id=None;self.orbit.setChecked(False)
        if self.frame is not None:
            # Returning never sends play or replaces the worker's state.
            self.on_message(self.frame)
        saved=self._saved_view or {};self.view.reset_camera()
        for key,value in saved.items():setattr(self.view,key,value)
        for checkbox,key in ((self.auto,'auto'),(self.orbit,'orbit'),(self.labels,'labels'),(self.halos,'halos'),(self.trails,'tracks'),(self.highlight_protection,'protect_highlights')):
            blocker=QSignalBlocker(checkbox);checkbox.setChecked(bool(getattr(self.view,key)));del blocker
        for key,slider in self.appearance_sliders.items():slider.setValue(round(getattr(self.view,key)*100))
        if hasattr(self.view,'_tracker'):
            self.view._tracker.reset(self.view.center/self.view._length_scale,self.view._manual_distance);self.view._tracking_target_key=None
        self._saved_view=None;self.set_illustration_controls(False)
        self.mode_title.setText('المحاكاة الحرّة / Free simulation')
        self.shape_description.setText('Photo-derived particle illustrations. Separate from the live gravity simulation.')
        self.update_control_state();self.view.update()

    def load_shape(self,ident,preview=False):
        if self.busy:return
        shape=get_shape(ident);self._active_shape_id=ident;self._pending_shape_id=ident
        self.shape_description.setText(shape['pair']+'. '+shape['description'])
        self.dirty=False;self.set_busy(True,'Evolving the suggested moment…' if preview else 'Preparing shape-inspired starting conditions…')
        self.command.emit({'action':'shape_setup','shape_id':ident,'preview':preview,'config':self.configuration()})

    def apply_shape_view(self,ident):
        shape=get_shape(ident)
        self.auto.setChecked(False);self.view.reset_camera()
        self.view.yaw=math.radians(shape['azimuth'])
        self.view.pitch=math.radians(90.-shape['elevation']) if hasattr(self.view,'canvas') else math.radians(shape['elevation'])
        self.palette_combo.setCurrentIndex(self.palette_combo.findData(shape['palette']))
        self.auto.setChecked(True);self._pending_shape_id=None;self.view.update()

    def build_encounter_controls(self,layout):
        self.encounter_group=QGroupBox('إعدادات جاهزة / Presets');box=QVBoxLayout(self.encounter_group)
        self.encounter_combo=QComboBox()
        for item in PRESETS:self.encounter_combo.addItem(item['label'],item['id'])
        self.encounter_combo.addItem('مخصّص — اضبط التفاصيل','custom')
        self.encounter_description=QLabel();self.encounter_description.setWordWrap(True)
        self.encounter_description.setStyleSheet('color:#a5bcd4;font-size:12px;')
        box.addWidget(self.encounter_combo);box.addWidget(self.encounter_description)
        self.encounter_combo.currentIndexChanged.connect(self.choose_encounter)
        layout.addWidget(self.encounter_group);self.physical_controls.append(self.encounter_combo)
        # Applied after the physical controls exist.
        QTimer.singleShot(0,self.sync_encounter)

    def sync_encounter(self):
        if not hasattr(self,'custom_settings'):return
        ident=match_config(self.configuration())
        blocker=QSignalBlocker(self.encounter_combo);self.encounter_combo.setCurrentIndex(self.encounter_combo.findData(ident));del blocker
        self.custom_settings.show()
        self.encounter_description.setText('غيّر القيم بالأسفل ثم طبّق الإعدادات.' if ident=='custom' else get_preset(ident)['description'])

    def choose_encounter(self,index):
        ident=self.encounter_combo.itemData(index)
        if not hasattr(self,'custom_settings'):return
        if ident=='custom':
            self.custom_settings.show()
            self.encounter_description.setText('غيّر القيم بالأسفل ثم طبّق الإعدادات.');return
        config=get_preset(ident)['config']
        self._active_shape_id=None;self.extra_config={'aligned_disks':False,'shape_id':''}
        controls=[*self.sliders.values(),self.spin,self.isolate,self.morphology_b]
        blockers=[QSignalBlocker(w) for w in controls]
        for key in ('impact','speed','massratio'):self.sliders[key].setValue(round(config[key]*100))
        self.sliders['inclination'].setValue(round(config['inclination']))
        self.spin.setCurrentIndex(0 if config['spin']==1 else 1);self.isolate.setChecked(config['isolated'])
        self.morphology_b.setCurrentIndex(0)
        del blockers
        self.dirty=True;self.apply_button.setText('تطبيق نمط اللقاء');self.update_labels();self.sync_encounter()
        self.update_control_state()

    def toggle_cinema(self):
        cinema=self.side.isVisible()
        self.side.setVisible(not cinema);self.camera_bar.setVisible(not cinema)

    @staticmethod
    def presenter_gpu_note():
        return ''

    @staticmethod
    def presenter_html():
        return '''<html dir="rtl"><h1 style="color:#ffd0ba">لقاء المجرّات</h1><h2>ابدأ بسؤال</h2><p>«لو مجرّتين اقتربوا من بعض… هل النجوم كلّها رح تضرب ببعض؟»</p><h2>شغّل المحاكاة</h2><p>«راقبوا اللونين؛ كل لون بيبيّن المجرّة اللي بدأت منها النجوم. الجاذبية بتغيّر حركة النجوم وبتعيد توزيعها. بعض النجوم ممكن تنسحب لذيول، وأحيانًا بنشوف جسر بين المجرّتين.»</p><p>«الاصطدام المباشر بين النجوم نادر لأن المسافات بينها هائلة. بالواقع الغاز كمان بيتفاعل، وممكن يساعد على ولادة نجوم جديدة. هذا البرنامج يحاكي الجاذبية وحركة نجوم ومادة مظلمة فقط؛ ما بنحاكي الغاز أو ولادة النجوم.»</p><h2>سلّم التحكّم</h2><p>«هلأ دورك: غيّر عاملًا واحدًا من شروط البداية وقارن حركة النجوم. توقّع النتيجة، وبعدين جرّب وشوف.»</p><h2>ليش نسخة Python أدق؟</h2><p>الحسابات هون ثلاثية الأبعاد. كل نقطة مادية بالعينة بتجذب النقاط الثانية، وفي هالات مادة مظلمة حيّة بتتفاعل. هذا بيسمح بتبادل الطاقة وانتزاع النجوم وتغيّر المدارات بدون رسم مسارات مسبقة أو إجبار المجرّات على الاندماج.</p><h2>حدود الدقّة</h2><p>هذا نموذج تعليمي منخفض الدقّة العددية مقارنة بمحاكاة بحثية: النقطة تمثّل عيّنة كبيرة، وليست نجمة حقيقية منفردة. بنستخدم تليينًا للجاذبية لتخفيف تأثير اللقاءات الاصطناعية بين نقاط العينة، وبداية المجرة بتكون في اتزان تقريبي بعد تهيئة ذاتية بالجاذبية. ما في غاز أو تشكّل نجوم أو نسبية عامة. الزمن بوحدات نموذجية، وليس تاريخًا حقيقيًا لمستقبل المجرّات.</p><h2>ملاحظات للمقدّم</h2><p>غيّر عاملًا واحدًا وقارن. Resolution يغيّر عدد جسيمات العينة؛ High أدق عددياً لكنه أبطأ. Playback يغيّر سرعة المشاهدة فقط. اختَر Dark matter لإظهار عيّنات الهالات؛ إخفاؤها ما بيلغي جاذبيتها. Diagnostics يعرض تغير الطاقة وعدد الجسيمات، وهو للمقدّم فقط.</p><p><a href="https://science.nasa.gov/missions/hubble/galaxies-collide/">NASA: المجرّات المتفاعلة</a></p></html>'''

    def configuration(self):
        return {**self.extra_config,'morphology_b':self.morphology_b.currentData(),'seed':self.seed,'count':self.quality.currentData(),'tracer_count':self.star_density.currentData(),'impact':self.sliders['impact'].value()/100,'speed':self.sliders['speed'].value()/100,'massratio':self.sliders['massratio'].value()/100,'inclination':float(self.sliders['inclination'].value()),'spin':1 if self.spin.currentIndex()==0 else -1,'isolated':self.isolate.isChecked()}

    def update_labels(self):
        raw={key:control.value() for key,control in self.sliders.items()}
        for key,value in raw.items():
            number=self.value_inputs[key];blocker=QSignalBlocker(number)
            number.setValue(value if key=='inclination' else value/100);del blocker
        impact=abs(raw['impact']);speed=raw['speed'];mass=raw['massratio'];tilt=raw['inclination']
        self.outputs['impact'].setText('قريب من المواجهة' if impact<40 else 'مرور واسع' if impact>230 else 'مرور جانبي')
        self.outputs['speed'].setText('بطيء نسبيًا' if speed<85 else 'سريع' if speed>135 else 'متوسط')
        self.outputs['massratio'].setText('كتلة متساوية' if mass==100 else f"ب = {mass}% من كتلة أ")
        self.outputs['inclination'].setText('مستويان متوازيان' if tilt==0 else 'ميل كبير' if tilt>50 else 'قرص مائل')

    def mark_dirty(self,*args):
        self.dirty=True;self.apply_button.setText('Apply new start *');self.update_labels()
        if self._active_shape_id:
            expected=get_shape(self._active_shape_id)['config'];actual=self.configuration()
            if any(actual.get(key)!=value for key,value in expected.items()):
                self._active_shape_id=None;self.extra_config['shape_id']=''
        if hasattr(self,'encounter_combo'):self.sync_encounter()
        if hasattr(self,'shape_preview_button'):self.update_control_state()

    def sync_config(self,cfg):
        blockers=[QSignalBlocker(w) for w in [*self.sliders.values(),self.spin,self.quality,self.star_density,self.isolate,self.morphology_b]]
        self.extra_config={key:cfg.get(key,default) for key,default in [('aligned_disks',False),('shape_id','')]}
        self.morphology_b.setCurrentIndex(self.morphology_b.findData(cfg.get('morphology_b','spiral')))
        self._active_shape_id=cfg.get('shape_id') if cfg.get('shape_id') in self.shape_buttons else None
        self.seed=int(cfg['seed']);self.sliders['impact'].setValue(round(cfg['impact']*100));self.sliders['speed'].setValue(round(cfg['speed']*100));self.sliders['massratio'].setValue(round(cfg['massratio']*100));self.sliders['inclination'].setValue(round(cfg['inclination']));self.spin.setCurrentIndex(0 if cfg['spin']==1 else 1);self.isolate.setChecked(cfg.get('isolated',False))
        star_index=self.star_density.findData(cfg.get('tracer_count',15000))
        if star_index>=0:self.star_density.setCurrentIndex(star_index)
        index=self.quality.findData(cfg['count'])
        if index>=0:self.quality.setCurrentIndex(index)
        del blockers;self.apply_button.setText('تطبيق نمط اللقاء');self.update_labels();self.sync_encounter()

    def send(self,action,**kwargs):
        if self.busy and action not in ('pause','rate'):return
        if self.illustration_id:
            if action=='reset':self.reference_camera();return
            if action in ('rewind','save','diagnostics'):return
            if action=='load':self.leave_illustration()
        if action=='reset' and self.frame is None:
            self.retry_preparation();return
        if action in ('reset','load'):self.dirty=False;self.set_busy(True,'Preparing Python state…')
        self.command.emit({'action':action,**kwargs})

    def set_busy(self,value,text=None,progress=0):
        if value and not self.busy:
            self.busy_since=time.monotonic()
            self.error_label.hide();self.last_error=None
        if value and text and text!=self.stage_text:
            self.stage_text=text;self.stage_since=time.monotonic()
        self.busy=value;self.busy_bar.setVisible(value);self.busy_bar.setValue(progress)
        if text:self.status.setText(text)
        for w in self.controls:w.setEnabled(not value)
        if value:
            self.play_button.setText('Preparing…');self.refresh_preparation()
        self.update_control_state()

    def refresh_preparation(self):
        if not self.busy:return
        elapsed=int(time.monotonic()-self.busy_since)
        text=f'{self.stage_text} · {elapsed}s elapsed'
        if time.monotonic()-self.stage_since >= 60:
            text+=' · This stage is taking longer than usual; first compilation can be slow.'
        self.status.setText(text)
        self.view.preparation_text=text+'\nPreparation progress describes stages, not remaining time.'
        self.view.update()

    def retry_preparation(self):
        self.set_busy(True,'Retrying galaxy preparation…')
        self.command.emit({'action':'setup',
                           'config':self.configuration(),'mode':self.mode})

    def update_control_state(self):
        running=bool(self.frame and self.frame['phase']=='running')
        for widget in self.physical_controls:widget.setEnabled(not self.busy and not running and not self.illustration_id)
        self.rewind_button.setEnabled(not self.busy and bool(self.frame) and not self.illustration_id)
        self.shape_preview_button.setEnabled(not self.busy and bool(self.illustration_id))
        self.save_checkpoint_button.setEnabled(not self.busy and not self.illustration_id)
        for ident,button in self.shape_buttons.items():button.setChecked(ident==self.illustration_id)

    def apply(self):
        if self.busy:return
        self.leave_illustration()
        self.dirty=False;self.apply_button.setText('Apply new starting conditions');self.set_busy(True,'Building the new physical starting state…');self.command.emit({'action':'apply','config':self.configuration()})

    def play(self):
        if self.busy:return
        if self.illustration_id:
            self.orbit.setChecked(not self.orbit.isChecked());self.view.setFocus();return
        if self.frame is None:
            self.retry_preparation();return
        if self.dirty and self.frame and self.frame['phase']!='running':self.apply()
        self.command.emit({'action':'play'});self.view.setFocus()

    def new(self):
        if self.busy:return
        self.leave_illustration()
        self.seed=secrets.randbits(32);rng=np.random.default_rng(self.seed)
        if self.mode=='simulation':
            self.sliders['impact'].setValue(int(rng.uniform(-260,260)));self.sliders['speed'].setValue(int(rng.uniform(65,145)));self.sliders['inclination'].setValue(int(rng.uniform(0,65)))
        self.dirty=False;self.set_busy(True,'Generating a new Python encounter…')
        self.command.emit({'action':'setup','config':self.configuration(),'mode':self.mode})
        self.camera_preset('reset')

    @Slot(object)
    def on_message(self,msg):
        kind=msg['type']
        if kind=='checkpoint':
            self.last_checkpoint=(msg['operation'],msg['path']);return
        if kind=='notice':
            self.set_busy(msg.get('busy',False),msg['text'],msg.get('progress',0));return
        if kind=='error':
            self.set_busy(False,'Physics stopped — see the error below.');
            self.last_error=msg
            text=f"Physics stopped during {msg.get('stage','preparation')}: {msg['text']}"
            self.error_label.setText(text);self.error_label.show()
            if self.frame:
                self.frame['phase']='paused';self.play_button.setText('Play / resume ▶');self.update_control_state()
            else:
                self.play_button.setText('Retry preparation');self.view.preparation_text=text+'\nUse Retry preparation, or choose Fast · 512 and retry.';self.view.update()
            QMessageBox.warning(self,'Simulation message',msg['text']);return
        if kind=='diagnostics':
            QMessageBox.information(self,'Python physics diagnostics',f"Particles: {msg['particles']:,}\nBackend: {msg['backend']}\nEnergy drift from start: {msg['drift']*100:.5f}%\nTotal momentum magnitude: {msg['momentum']:.3g}\nAngular momentum magnitude: {msg['angular']:.6g}\nRecent force/integration step: {msg['step_ms']:.2f} ms\n\nConservation checks measure numerical integration quality, not whether this simplified galaxy model is a precise real-galaxy prediction.");return
        if kind!='frame':return
        previous=self.frame
        self.frame=msg;self.mode=msg['mode']
        if self.illustration_id:return
        self.view.set_data(msg)
        if self._pending_shape_id and msg['config'].get('shape_id')==self._pending_shape_id:self.apply_shape_view(self._pending_shape_id)
        # Live geometry has its own 60 Hz GPU clock. Avoid rebuilding the
        # sidebar and relaying out status text for every physics frame.
        continuing=(not self.busy and previous is not None and msg['phase']=='running'
                    and previous['phase']=='running' and previous['mode']==msg['mode']
                    and previous['config']==msg['config'])
        if continuing:
            now=time.monotonic()
            if now-getattr(self,'_last_live_status',0.)>=.2:
                self._last_live_status=now
                self.time_bar.setValue(min(1000,round(msg['time']/END_TIME*1000)))
                self.status.setText(f"RUNNING · {msg['count']:,} gravity particles · {msg['backend']} · model time {msg['time']:.2f} · {msg['step_ms']:.1f} ms / step")
            return
        self.set_busy(False)
        self.error_label.hide();self.last_error=None
        if not self.dirty:self.sync_config(msg['config'])
        phase=msg['phase'];self.play_button.setText('Pause Ⅱ' if phase=='running' else 'Launch encounter →' if phase=='ready' else 'Play / resume ▶')
        self.time_bar.setValue(min(1000,round(msg['time']/END_TIME*1000)))
        self.goal_title.setText('Explore live self-gravity')
        self.goal_copy.setText('Adjust the numbers below, apply, then compare. Change one starting condition at a time.')
        self.mode_note.setText('Free simulation · values use model units; playback changes viewing speed only.')
        self.status.setText(f"{phase.upper()} · {msg['count']:,} particles · {msg['backend']} · model time {msg['time']:.2f} · {msg['step_ms']:.1f} ms / step")
        if msg['backend']=='NumPy':self.status.setText(self.status.text()+' · Install Numba for faster execution')
        self.update_control_state()

    def camera_preset(self,kind):
        if kind=='reset' and self.illustration_id:self.reference_camera();return
        if kind=='reset':self.view.reset_camera();self.auto.setChecked(self.view.auto)
        elif kind=='top':self.view.yaw=0;self.view.pitch=0;self.view.update()
        elif kind=='oblique':self.view.yaw=math.radians(30) if hasattr(self.view,'canvas') else -.35;self.view.pitch=math.radians(65) if hasattr(self.view,'canvas') else .62;self.view.update()
        else:self.view.yaw=0;self.view.pitch=math.pi/2;self.view.update()
    def zoom(self,factor):self.view.zoom=float(np.clip(self.view.zoom*factor,.25,5));self.view.update()
    def fullscreen(self):self.showNormal() if self.isFullScreen() else self.showFullScreen()
    def exit_fullscreen(self):
        if self.isFullScreen():self.showNormal()
    def screenshot(self):
        if self.frame is None:return
        name=f'{self.illustration_id}-illustration.png' if self.illustration_id else 'galaxy-encounter.png'
        path,_=QFileDialog.getSaveFileName(self,'Save view',name,'PNG image (*.png)')
        if path:
            image=self.view.capture() if hasattr(self.view,'capture') else self.view.grab()
            if not image.save(path,'PNG'):QMessageBox.warning(self,'Save image','Could not save the image.')
    def save_checkpoint(self):
        if self.busy or self.illustration_id:return
        self.command.emit({'action':'pause'});path,_=QFileDialog.getSaveFileName(self,'Save Python state','galaxy-checkpoint.npz','NumPy checkpoint (*.npz)')
        if path:self.send('save',path=path)
    def load_checkpoint(self):
        if self.busy:return
        self.command.emit({'action':'pause'});path,_=QFileDialog.getOpenFileName(self,'Load Python state','','NumPy checkpoint (*.npz)')
        if path:self.leave_illustration();self.send('load',path=path)
    def closeEvent(self,event):
        self.render_timer.stop();self.preparation_timer.stop();self.worker.cancel_job.set();self.thread.requestInterruption();self.thread.quit()
        if self.thread.wait(2000):
            if hasattr(self.view,'shutdown'):self.view.shutdown()
            event.accept()
        else:
            event.ignore();self.status.setText('Finishing the current physics operation before closing…');QTimer.singleShot(400,self.close)
