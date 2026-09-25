"""Offline UI preview with synthetic status; never connects to a game."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import struct
import tempfile
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap,QPainter,QColor
from native_overlay import OverlayController,STYLE,app_icon,describe_state
from native_settings import load_cjk_font
from native_config import write_config,DEFAULTS

app=QApplication([]);load_cjk_font(app);app.setStyleSheet(STYLE)
output=Path(__file__).resolve().parents[1]/'generated';output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    control=Path(tmp)/'control.json';status=Path(tmp)/'status.json';write_config(DEFAULTS,control)
    controller=OverlayController(control,status,start_timers=False);controller.expand()
    controller.panel.settings._status_timer.stop();controller.panel.settings._capture_timer.stop()
    live=dict(running=True,updated_at=100,primary='zh-Hans',secondary='ja',interaction='language_hold',render_mode='primary')
    config={**DEFAULTS,'interaction':'language_hold'}
    released=describe_state(config,live,{},100)
    held=describe_state(config,{**live,'hold_active':True,'render_mode':'secondary'},{},100)
    controller.panel.settings._set_combo(controller.panel.settings.interaction,'language_hold')
    controller.panel.present(released)
    controller.panel.settings.backend_label.setText('离线界面演示 · 未启动或连接游戏')
    for index,name in enumerate(('mode','layout','bindings','updates')):
        controller.panel.settings.tabs.setCurrentIndex(index);app.processEvents()
        controller.panel.grab().save(str(output/f'overlay-{name}-preview.png'))
    controller.bar.present(released,'Ctrl + Shift + F9');controller.bar.adjustSize();controller.bar.show();app.processEvents()
    first=controller.bar.grab();controller.bar.present(held,'Ctrl + Shift + F9');app.processEvents();second=controller.bar.grab()
    composite=QPixmap(max(first.width(),second.width()),first.height()+second.height()+16);composite.fill(QColor('#0d141d'))
    painter=QPainter(composite);painter.drawPixmap(0,0,first);painter.drawPixmap(0,first.height()+16,second);painter.end()
    composite.save(str(output/'overlay-hold-preview.png'))
    controller.bar.hide();controller.panel.hide();controller.tray.hide()
icon_path=output/'sora-bilingual-icon.png';app_icon().pixmap(64,64).save(str(icon_path))
data=icon_path.read_bytes()
(output/'sora-bilingual.ico').write_bytes(struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',64,64,0,0,1,32,len(data),22)+data)
print('Offline previews saved:',output)
