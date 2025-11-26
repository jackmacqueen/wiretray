import sys
import os
import subprocess
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, 
                             QWidget, QSystemTrayIcon, QMenu, QPushButton, 
                             QMessageBox, QListWidget, QListWidgetItem, QHBoxLayout)
from PyQt6.QtGui import QAction, QIcon, QPainter, QColor
from PyQt6.QtCore import QSize, QTimer, Qt

# Configuration
WG_DIR = "/etc/wireguard"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("WireTray")
        self.setMinimumSize(QSize(400, 450))
        self.configs = [] # List of config names (e.g., ['wg0', 'wg1'])

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
        self.tray_icon.setIcon(self.create_status_icon(False))
        
        # We build the menu dynamically in update_tray_menu
        self.tray_menu = QMenu()
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

        # Handle clicking the icon itself (Left click)
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
                # We can't use MessageBox here easily if it runs on startup loop, 
                # so we show error in list
                item = QListWidgetItem("Error: /etc/wireguard not found")
                self.list_widget.addItem(item)
                return

            files = os.listdir(WG_DIR)
            for f in files:
                if f.endswith(".conf"):
                    config_name = f.replace(".conf", "")
                    self.configs.append(config_name)
                    
            self.configs.sort()
            
            # Populate List Widget
            for config in self.configs:
                item = QListWidgetItem(config)
                # FIX: Store the "clean" name in hidden data so we don't break it when changing text
                item.setData(Qt.ItemDataRole.UserRole, config) 
                self.list_widget.addItem(item)
                
            self.update_tray_menu()
            
        except PermissionError:
            self.list_widget.addItem("Permission Denied: /etc/wireguard")
            self.list_widget.addItem("Run: sudo chmod o+rx /etc/wireguard")

    def update_tray_menu(self):
        """Rebuilds the tray menu with available configs."""
        self.tray_menu.clear()
        
        # Add Actions for each config
        for config in self.configs:
            action = QAction(config, self)
            # We use a lambda with default arg to capture the specific config string
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
        """Checks status of all configs and updates UI."""
        any_active = False
        
        # 1. Update List Widget
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            
            # FIX: Retrieve the clean name from hidden data
            name = item.data(Qt.ItemDataRole.UserRole)
            
            # Skip items that aren't configs (like error messages)
            if not name:
                continue
                
            active = self.is_interface_active(name)
            if active:
                any_active = True
                item.setIcon(QIcon.fromTheme("network-transmit-receive"))
                item.setText(f"{name} (Active)")
                item.setForeground(QColor("#4CAF50")) # Green text
            else:
                item.setIcon(QIcon.fromTheme("network-offline"))
                item.setText(name)
                # Reset color based on theme (light/dark mode safe-ish)
                item.setForeground(QColor(0,0,0) if self.palette().windowText().color().lightness() < 128 else QColor(255,255,255))

        # 2. Update Tray Menu Text/Icons
        actions = self.tray_menu.actions()
        for action in actions:
            # We check if the action text starts with a known config name
            # This is a bit loose, but works since we rebuild menu on scan
            # A cleaner way would be to store data in actions too, but this works.
            current_text = action.text()
            # Strip existing status to find the name
            clean_name = current_text.replace("  [Active]", "")
            
            if clean_name in self.configs:
                active = self.is_interface_active(clean_name)
                if active:
                    action.setText(f"{clean_name}  [Active]")
                else:
                    action.setText(f"{clean_name}")

        # 3. Update Main Tray Icon
        self.tray_icon.setIcon(self.create_status_icon(any_active))
        self.setWindowIcon(self.create_status_icon(any_active))

    def create_status_icon(self, active):
        base_icon = QIcon.fromTheme("network-vpn")
        if base_icon.isNull():
            base_icon = QIcon.fromTheme("network-wired")

        pixmap = base_icon.pixmap(64, 64)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dot color
        color = QColor("#4CAF50") if active else QColor("#F44336") 
        
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        
        dot_size = 24
        x = 64 - dot_size
        y = 64 - dot_size
        painter.drawEllipse(x, y, dot_size, dot_size)
        painter.end()
        return QIcon(pixmap)

    def on_list_double_click(self, item):
        # FIX: Use data instead of text splitting
        name = item.data(Qt.ItemDataRole.UserRole)
        if name and name in self.configs:
            self.toggle_vpn(name)

    def toggle_selected(self):
        current_item = self.list_widget.currentItem()
        if current_item:
            # FIX: Use data instead of text splitting
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
                # Force immediate update
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