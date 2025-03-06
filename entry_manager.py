import os
import json
import sqlite3
from datetime import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QLineEdit, QTextEdit, QPushButton, QListWidget,
                            QMessageBox, QInputDialog, QComboBox)
from PyQt6.QtCore import Qt, QSize

class EntryDatabase:
    """Handles database operations for saved entries"""
    
    def __init__(self):
        # Create database directory if it doesn't exist
        self.db_dir = os.path.join(os.path.expanduser("~"), ".medical_recipe_editor")
        os.makedirs(self.db_dir, exist_ok=True)
        
        # Connect to database
        self.db_path = os.path.join(self.db_dir, "entries.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        
        # Create tables if they don't exist
        self._create_tables()
    
    def _create_tables(self):
        """Create necessary tables if they don't exist"""
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS entry_categories (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE
        )
        ''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY,
            category_id INTEGER,
            title TEXT,
            content TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (category_id) REFERENCES entry_categories (id)
        )
        ''')
        
        # Insert default categories if they don't exist
        default_categories = [
            "diagnostico",
            "plan_tratamiento",
            "rutina_am",
            "rutina_pm",
            "recomendacion",
            "proxima_cita"
        ]
        
        for category in default_categories:
            self.cursor.execute(
                "INSERT OR IGNORE INTO entry_categories (name) VALUES (?)",
                (category,)
            )
        
        self.conn.commit()
    
    def get_entries(self, category):
        """Get all entries for a specific category"""
        self.cursor.execute('''
        SELECT id, title, content, created_at, updated_at
        FROM entries
        WHERE category_id = (SELECT id FROM entry_categories WHERE name = ?)
        ORDER BY updated_at DESC
        ''', (category,))
        
        return self.cursor.fetchall()
    
    def get_entry(self, entry_id):
        """Get a specific entry by ID"""
        self.cursor.execute('''
        SELECT id, title, content, created_at, updated_at
        FROM entries
        WHERE id = ?
        ''', (entry_id,))
        
        return self.cursor.fetchone()
    
    def add_entry(self, category, title, content):
        """Add a new entry"""
        now = datetime.now().isoformat()
        
        self.cursor.execute('''
        INSERT INTO entries (category_id, title, content, created_at, updated_at)
        VALUES ((SELECT id FROM entry_categories WHERE name = ?), ?, ?, ?, ?)
        ''', (category, title, content, now, now))
        
        self.conn.commit()
        return self.cursor.lastrowid
    
    def update_entry(self, entry_id, title, content):
        """Update an existing entry"""
        now = datetime.now().isoformat()
        
        self.cursor.execute('''
        UPDATE entries
        SET title = ?, content = ?, updated_at = ?
        WHERE id = ?
        ''', (title, content, now, entry_id))
        
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def delete_entry(self, entry_id):
        """Delete an entry"""
        self.cursor.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()

class EntryManagerDialog(QDialog):
    """Dialog for managing entries (add, edit, delete)"""
    
    def __init__(self, category, parent=None):
        super().__init__(parent)
        self.category = category
        self.db = EntryDatabase()
        self.selected_entry_id = None
        
        # Map category to display name
        category_display_names = {
            "diagnostico": "Diagnóstico",
            "plan_tratamiento": "Plan de Tratamiento",
            "rutina_am": "Rutina Facial (AM)",
            "rutina_pm": "Rutina Facial (PM)",
            "recomendacion": "Recomendación Antiestres y Performance",
            "proxima_cita": "Próxima Cita Médica"
        }
        
        self.display_name = category_display_names.get(category, category.capitalize())
        
        self.initUI()
        self.loadEntries()
    
    def initUI(self):
        self.setWindowTitle(f"Gestionar Entradas - {self.display_name}")
        self.setMinimumSize(600, 500)
        
        layout = QVBoxLayout()
        
        # Entry list
        list_label = QLabel("Entradas guardadas:")
        self.entry_list = QListWidget()
        self.entry_list.setMinimumHeight(150)
        self.entry_list.currentRowChanged.connect(self.onEntrySelected)
        
        # Entry details
        details_layout = QVBoxLayout()
        
        title_layout = QHBoxLayout()
        title_label = QLabel("Título:")
        self.title_edit = QLineEdit()
        title_layout.addWidget(title_label)
        title_layout.addWidget(self.title_edit)
        
        content_label = QLabel("Contenido:")
        self.content_edit = QTextEdit()
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.new_btn = QPushButton("Nueva Entrada")
        self.new_btn.clicked.connect(self.onNewEntry)
        
        self.save_btn = QPushButton("Guardar")
        self.save_btn.clicked.connect(self.onSaveEntry)
        
        self.delete_btn = QPushButton("Eliminar")
        self.delete_btn.clicked.connect(self.onDeleteEntry)
        self.delete_btn.setEnabled(False)
        
        self.use_btn = QPushButton("Usar Esta Entrada")
        self.use_btn.clicked.connect(self.accept)
        self.use_btn.setEnabled(False)
        
        button_layout.addWidget(self.new_btn)
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.use_btn)
        
        # Add widgets to layout
        layout.addWidget(list_label)
        layout.addWidget(self.entry_list)
        layout.addLayout(title_layout)
        layout.addWidget(content_label)
        layout.addWidget(self.content_edit)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def loadEntries(self):
        """Load entries from database into list widget"""
        self.entry_list.clear()
        entries = self.db.get_entries(self.category)
        
        for entry in entries:
            entry_id, title, content, created_at, updated_at = entry
            self.entry_list.addItem(title)
        
        # Store entry IDs
        self.entry_ids = [entry[0] for entry in entries]
    
    def onEntrySelected(self, row):
        """Handle entry selection from list"""
        if row >= 0 and row < len(self.entry_ids):
            entry_id = self.entry_ids[row]
            self.selected_entry_id = entry_id
            
            entry = self.db.get_entry(entry_id)
            if entry:
                _, title, content, _, _ = entry
                self.title_edit.setText(title)
                self.content_edit.setText(content)
                self.delete_btn.setEnabled(True)
                self.use_btn.setEnabled(True)
        else:
            self.selected_entry_id = None
            self.title_edit.clear()
            self.content_edit.clear()
            self.delete_btn.setEnabled(False)
            self.use_btn.setEnabled(False)
    
    def onNewEntry(self):
        """Create a new entry"""
        self.selected_entry_id = None
        self.title_edit.clear()
        self.content_edit.clear()
        self.entry_list.clearSelection()
        self.delete_btn.setEnabled(False)
        self.use_btn.setEnabled(False)
        self.title_edit.setFocus()
    
    def onSaveEntry(self):
        """Save current entry"""
        title = self.title_edit.text().strip()
        content = self.content_edit.toPlainText().strip()
        
        if not title:
            QMessageBox.warning(self, "Error", "Por favor ingrese un título para la entrada.")
            return
        
        if not content:
            QMessageBox.warning(self, "Error", "Por favor ingrese contenido para la entrada.")
            return
        
        try:
            if self.selected_entry_id is None:
                # Add new entry
                self.db.add_entry(self.category, title, content)
                QMessageBox.information(self, "Éxito", "Entrada guardada correctamente.")
            else:
                # Update existing entry
                self.db.update_entry(self.selected_entry_id, title, content)
                QMessageBox.information(self, "Éxito", "Entrada actualizada correctamente.")
            
            # Reload entries
            self.loadEntries()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al guardar la entrada: {str(e)}")
    
    def onDeleteEntry(self):
        """Delete selected entry"""
        if self.selected_entry_id is None:
            return
        
        confirm = QMessageBox.question(
            self, "Confirmar Eliminación",
            "¿Está seguro de que desea eliminar esta entrada? Esta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                self.db.delete_entry(self.selected_entry_id)
                self.loadEntries()
                self.onNewEntry()  # Clear form
                QMessageBox.information(self, "Éxito", "Entrada eliminada correctamente.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al eliminar la entrada: {str(e)}")
    
    def getSelectedEntry(self):
        """Return the selected entry data"""
        if self.selected_entry_id is not None:
            return {
                "id": self.selected_entry_id,
                "title": self.title_edit.text(),
                "content": self.content_edit.toPlainText()
            }
        return None
    
    def closeEvent(self, event):
        """Close database connection when dialog is closed"""
        self.db.close()
        super().closeEvent(event)

class EntrySelector(QComboBox):
    """Custom ComboBox for selecting saved entries"""
    
    def __init__(self, category, parent=None):
        super().__init__(parent)
        self.category = category
        self.db = EntryDatabase()
        self.entries = []
        
        # Add placeholder item
        self.addItem("-- Seleccionar entrada guardada --")
        
        # Add manage entries option
        self.addItem("✏️ Gestionar entradas...")
        
        # Load entries
        self.loadEntries()
        
        # Connect signals
        self.currentIndexChanged.connect(self.onSelectionChanged)
    
    def loadEntries(self):
        """Load entries from database"""
        # Clear existing entries (keep first two items)
        while self.count() > 2:
            self.removeItem(2)
        
        # Get entries from database
        self.entries = self.db.get_entries(self.category)
        
        # Add entries to combo box
        for entry in self.entries:
            entry_id, title, content, created_at, updated_at = entry
            self.addItem(title)
    
    def onSelectionChanged(self, index):
        """Handle selection change"""
        if index == 1:  # "Manage entries" option
            # Reset selection
            self.setCurrentIndex(0)
            
            # Open entry manager dialog
            dialog = EntryManagerDialog(self.category, self.parent())
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # User selected an entry
                selected_entry = dialog.getSelectedEntry()
                if selected_entry:
                    # Reload entries
                    self.loadEntries()
                    
                    # Find and select the entry in the combo box
                    for i in range(2, self.count()):
                        if self.itemText(i) == selected_entry['title']:
                            self.setCurrentIndex(i)
                            break
                    
                    # Get the main window (MedicalRecipeEditor)
                    main_window = self.parent().window()
                    
                    # Find the associated field based on category
                    field_map = {
                        'diagnostico': main_window.diagnostico_edit,
                        'plan_tratamiento': main_window.plan_tratamiento_edit,
                        'rutina_am': main_window.rutina_am_edit,
                        'rutina_pm': main_window.rutina_pm_edit,
                        'recomendacion': main_window.recomendacion_edit
                    }
                    
                    field = field_map.get(self.category)
                    if field:
                        main_window.load_entry_content(self, field)
            
            # Reload entries in case they were modified
            self.loadEntries()
        elif index > 1 and index - 2 < len(self.entries):
            # Get the main window (MedicalRecipeEditor)
            main_window = self.parent().window()
            
            # Find the associated field based on category
            field_map = {
                'diagnostico': main_window.diagnostico_edit,
                'plan_tratamiento': main_window.plan_tratamiento_edit,
                'rutina_am': main_window.rutina_am_edit,
                'rutina_pm': main_window.rutina_pm_edit,
                'recomendacion': main_window.recomendacion_edit
            }
            
            field = field_map.get(self.category)
            if field:
                main_window.load_entry_content(self, field)
        
        return None
    
    def getSelectedEntry(self):
        """Get the currently selected entry"""
        index = self.currentIndex()
        if index > 1 and index - 2 < len(self.entries):
            entry_id, title, content, created_at, updated_at = self.entries[index - 2]
            return {
                "id": entry_id,
                "title": title,
                "content": content
            }
        return None 