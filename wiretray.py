import sys
import os
import subprocess
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, 
                             QWidget, QSystemTrayIcon, QMenu, QPushButton, 
                             QMessageBox, QListWidget, QListWidgetItem, QHBoxLayout)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import QAction, QIcon, QPainter, QColor
from PyQt6.QtCore import QSize, QTimer, Qt

# Configuration
WG_DIR = "/etc/wireguard"

# --- HELPER FUNCTION ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Initial Icon Load
        self.setWindowIcon(QIcon(resource_path("icon.svg")))

        self.setWindowTitle("WireTray")
        self.setMinimumSize(QSize(400, 450))
        self.configs = [] 

        # --- GUI Setup ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Available Connections")
        font = title.font()
        font.setPointSize(12)
        font.setBold(True)
        title.setFont(font)
        header_layout.addWidget(title)
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFixedWidth(80)
        self.refresh_btn.clicked.connect(self.scan_configs)
        header_layout.addWidget(self.refresh_btn)
        layout.addLayout(header_layout)

        # Help Label
        help_lbl = QLabel("WireGuard conf files are read from /etc/wireguard/")
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(help_lbl)

        # Config List
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.on_list_double_click)
        layout.addWidget(self.list_widget)

        # Controls
        btn_layout = QHBoxLayout()
        self.toggle_btn = QPushButton("Toggle Selected")
        self.toggle_btn.clicked.connect(self.toggle_selected)
        btn_layout.addWidget(self.toggle_btn)
        layout.addLayout(btn_layout)

        # --- System Tray Setup ---
        self.tray_icon = QSystemTrayIcon(self)
        
        # Initialize menu
        self.tray_menu = QMenu()
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

        self.tray_icon.activated.connect(self.on_tray_icon_click)

        # --- Timer for Status Updates ---
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(2000)

        # Initial Load
        self.scan_configs()
        self.update_status()

    def scan_configs(self):
        """Scans the WireGuard directory for .conf files."""
        self.configs = []
        self.list_widget.clear()
        
        try:
            if not os.path.exists(WG_DIR):
                item = QListWidgetItem("Error: /etc/wireguard not found")
                self.list_widget.addItem(item)
                return

            files = os.listdir(WG_DIR)
            for f in files:
                if f.endswith(".conf"):
                    config_name = f.replace(".conf", "")
                    self.configs.append(config_name)
                    
            self.configs.sort()
            
            for config in self.configs:
                item = QListWidgetItem(config)
                item.setData(Qt.ItemDataRole.UserRole, config) 
                self.list_widget.addItem(item)
                
            self.update_tray_menu()
            
        except PermissionError:
            self.list_widget.addItem("Permission Denied: /etc/wireguard")
            self.list_widget.addItem("Run: sudo chmod o+rx /etc/wireguard")

    def update_tray_menu(self):
        """Rebuilds the tray menu with available configs."""
        self.tray_menu.clear()
        
        for config in self.configs:
            action = QAction(config, self)
            action.triggered.connect(lambda checked, c=config: self.toggle_vpn(c))
            self.tray_menu.addAction(action)

        self.tray_menu.addSeparator()

        restore_action = QAction("Show Controls", self)
        restore_action.triggered.connect(self.show_window)
        self.tray_menu.addAction(restore_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        self.tray_menu.addAction(quit_action)

    def is_interface_active(self, interface):
        return os.path.exists(f"/sys/class/net/{interface}")

    def update_status(self):
        any_active = False
        
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            name = item.data(Qt.ItemDataRole.UserRole)
            
            if not name:
                continue
                
            active = self.is_interface_active(name)
            if active:
                any_active = True
                item.setIcon(QIcon.fromTheme("network-transmit-receive"))
                item.setText(f"{name} (Active)")
                item.setForeground(QColor("#4CAF50"))
            else:
                item.setIcon(QIcon.fromTheme("network-offline"))
                item.setText(name)
                # Use theme-aware text color for list items
                item.setForeground(QColor(0,0,0) if self.get_is_light_theme() else QColor(255,255,255))

        actions = self.tray_menu.actions()
        for action in actions:
            current_text = action.text()
            clean_name = current_text.replace("  [Active]", "")
            
            if clean_name in self.configs:
                active = self.is_interface_active(clean_name)
                if active:
                    action.setText(f"{clean_name}  [Active]")
                else:
                    action.setText(f"{clean_name}")

        self.tray_icon.setIcon(self.create_status_icon(any_active))
        self.setWindowIcon(self.create_status_icon(any_active))

    def get_is_light_theme(self):
        return self.palette().color(self.palette().ColorRole.WindowText).lightness() < 128

    def create_status_icon(self, active):
        
        icon_path = resource_path("icon.svg")
        base_icon = QIcon(icon_path)
        if base_icon.isNull():
            base_icon = QIcon.fromTheme("network-vpn")

        pixmap = base_icon.pixmap(64, 64)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_light_mode = self.get_is_light_theme()
        
        icon_color = QColor("black") if is_light_mode else QColor("white")
        
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), icon_color)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        
        dot_color = QColor("#4CAF50") if active else QColor("#F44336") 
        painter.setBrush(dot_color)
        painter.setPen(Qt.PenStyle.NoPen)
        
        dot_size = 24
        x = 64 - dot_size
        y = 64 - dot_size
        painter.drawEllipse(x, y, dot_size, dot_size)
        
        painter.end()
        return QIcon(pixmap)

    def on_list_double_click(self, item):
        name = item.data(Qt.ItemDataRole.UserRole)
        if name and name in self.configs:
            self.toggle_vpn(name)

    def toggle_selected(self):
        current_item = self.list_widget.currentItem()
        if current_item:
            name = current_item.data(Qt.ItemDataRole.UserRole)
            if name and name in self.configs:
                self.toggle_vpn(name)

    def toggle_vpn(self, interface):
        active = self.is_interface_active(interface)
        command = "down" if active else "up"
        
        cmd_list = ["sudo", "wg-quick", command, interface]
        
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            result = subprocess.run(cmd_list, capture_output=True, text=True)
            
            if result.returncode != 0:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self, "Error", f"Failed to toggle {interface}:\n{result.stderr}")
            else:
                self.update_status()
                
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        
    def show_window(self):
        self.show()
        self.activateWindow()

    def on_tray_icon_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def quit_app(self):
        self.tray_icon.hide()
        QApplication.instance().quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())