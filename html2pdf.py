import os
import sys
import tempfile
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QTextEdit, 
                            QPushButton, QFileDialog, QFormLayout, QGroupBox,
                            QDateEdit, QSpinBox, QComboBox, QMessageBox,
                            QScrollArea, QFrame, QSizePolicy, QDialog,
                            QDialogButtonBox, QFontComboBox, QCheckBox)
from PyQt6.QtCore import Qt, QDate, QRect, QPoint, QSizeF
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QPageSize, QScreen
from PyQt6.QtPrintSupport import QPrinter

# Since PyQt6-PDF doesn't exist, let's use an alternative approach
# We'll use fitz (PyMuPDF) for PDF rendering
import fitz  # PyMuPDF
from reportlab.pdfgen import canvas
from PyPDF2 import PdfReader, PdfWriter

class PDFPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_document = None
        self.template_pdf_path = None
        self.current_page = 0
        self.pixmap = None
        self.scale_factor = 1.0
        self.selection_rect = None
        self.start_point = None
        self.end_point = None
        self.is_selecting = False
        self.pdf_rect = None  # Store the actual PDF rectangle in widget coordinates
        self.setMinimumSize(400, 500)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        
    def load_pdf(self, path):
        try:
            # Use PyMuPDF (fitz) to open the PDF
            self.pdf_document = fitz.open(path)
            if len(self.pdf_document) > 0:
                self.current_page = 0
                
                # Calculate appropriate scale factor based on widget size
                page = self.pdf_document[self.current_page]
                page_width = page.rect.width
                page_height = page.rect.height
                
                # Calculate scale factor to fit the widget while maintaining aspect ratio
                width_scale = (self.width() - 40) / page_width  # 20px margin on each side
                height_scale = (self.height() - 40) / page_height  # 20px margin on each side
                self.scale_factor = min(width_scale, height_scale)
                
                self.update_preview()
                return True
            return False
        except Exception as e:
            print(f"Error loading PDF: {e}")
            return False
    
    def update_preview(self):
        if not self.pdf_document or len(self.pdf_document) <= 0:
            return
        
        try:
            # Get the current page
            page = self.pdf_document[self.current_page]
            
            # Create a matrix to scale the page
            matrix = fitz.Matrix(self.scale_factor, self.scale_factor)
            
            # Render page to a PyMuPDF Pixmap
            pix = page.get_pixmap(matrix=matrix)
            
            # Convert PyMuPDF Pixmap to QPixmap
            img_data = pix.samples
            
            from PyQt6.QtGui import QImage
            img_format = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
            
            qimage = QImage(img_data, pix.width, pix.height, pix.stride, img_format)
            
            self.pixmap = QPixmap.fromImage(qimage)
            
            # Calculate the PDF rectangle in widget coordinates
            x = (self.width() - self.pixmap.width()) / 2
            y = (self.height() - self.pixmap.height()) / 2
            self.pdf_rect = QRect(int(x), int(y), self.pixmap.width(), self.pixmap.height())
            
            # Reset selection when loading a new PDF
            self.selection_rect = None
            self.start_point = None
            self.end_point = None
            
            # Update the widget
            self.update()
            
        except Exception as e:
            print(f"Error updating preview: {e}")
    
    def resizeEvent(self, event):
        # Recalculate PDF position when widget is resized
        if self.pixmap:
            x = (self.width() - self.pixmap.width()) / 2
            y = (self.height() - self.pixmap.height()) / 2
            self.pdf_rect = QRect(int(x), int(y), self.pixmap.width(), self.pixmap.height())
        super().resizeEvent(event)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        
        # Draw white background
        painter.fillRect(event.rect(), Qt.GlobalColor.white)
        
        if self.pixmap:
            # Draw the PDF preview centered
            painter.drawPixmap(self.pdf_rect, self.pixmap)
            
            # Draw a border around the PDF
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.drawRect(self.pdf_rect)
            
            # Draw the selection rectangle if it exists
            if self.selection_rect:
                painter.setPen(QPen(QColor(255, 0, 0), 2, Qt.PenStyle.DashLine))
                painter.drawRect(self.selection_rect)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.pdf_rect:
            # Check if click is inside the PDF area
            if self.pdf_rect.contains(event.position().toPoint()):
                # Start selection
                self.is_selecting = True
                self.start_point = event.position().toPoint()
                self.end_point = self.start_point
                self.selection_rect = QRect(self.start_point, self.end_point)
                self.update()
    
    def mouseMoveEvent(self, event):
        if self.is_selecting and self.pdf_rect:
            # Update end point, but constrain to PDF area
            current_pos = event.position().toPoint()
            
            # Constrain to PDF boundaries
            x = max(self.pdf_rect.left(), min(current_pos.x(), self.pdf_rect.right()))
            y = max(self.pdf_rect.top(), min(current_pos.y(), self.pdf_rect.bottom()))
            
            self.end_point = QPoint(x, y)
            
            # Update selection rectangle
            self.selection_rect = QRect(self.start_point, self.end_point).normalized()
            self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.is_selecting = False
            
            # Finalize selection rectangle
            if self.start_point and self.end_point:
                self.selection_rect = QRect(self.start_point, self.end_point).normalized()
                
                # If the selection is too small, ignore it
                if self.selection_rect.width() < 10 or self.selection_rect.height() < 10:
                    self.selection_rect = None
                
                self.update()
    
    def get_selection_rect(self):
        # Return the selection rectangle scaled back to the original PDF coordinates
        if self.selection_rect and self.pdf_rect:
            # Convert from widget coordinates to PDF coordinates
            rel_x = self.selection_rect.x() - self.pdf_rect.x()
            rel_y = self.selection_rect.y() - self.pdf_rect.y()
            
            # Scale back to original PDF coordinates
            orig_x = int(rel_x / self.scale_factor)
            orig_y = int(rel_y / self.scale_factor)
            orig_width = int(self.selection_rect.width() / self.scale_factor)
            orig_height = int(self.selection_rect.height() / self.scale_factor)
            
            return QRect(orig_x, orig_y, orig_width, orig_height)
        return None

    def update_with_overlay(self, overlay_path):
        if not self.pdf_document:
            return
        
        try:
            # Create a temporary merged PDF
            temp_merged = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            temp_merged.close()
            
            # Merge the template with the overlay
            self.merge_pdfs(self.template_pdf_path, overlay_path, temp_merged.name)
            
            # Update the preview with the merged PDF
            self.load_pdf(temp_merged.name)
            
            # Clean up
            os.unlink(temp_merged.name)
            
        except Exception as e:
            print(f"Error updating preview: {e}")

    def set_template_path(self, path):
        self.template_pdf_path = path

    def merge_pdfs(self, template_path, overlay_path, output_path):
        # Read the template PDF
        template_pdf = PdfReader(template_path)
        
        # Read the overlay PDF
        overlay_pdf = PdfReader(overlay_path)
        
        # Create a PDF writer
        output = PdfWriter()
        
        # Merge pages
        for i in range(len(template_pdf.pages)):
            template_page = template_pdf.pages[i]
            
            # If we have an overlay page for this template page
            if i < len(overlay_pdf.pages):
                template_page.merge_page(overlay_pdf.pages[i])
            
            output.add_page(template_page)
        
        # Write the output PDF
        with open(output_path, 'wb') as output_file:
            output.write(output_file)

class MedicalRecipeEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.template_pdf_path = None
        self.working_area = None
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle('Editor de Recetas Médicas')
        
        # Get the screen geometry
        screen = QApplication.primaryScreen().geometry()
        
        # Calculate window size (80% of screen size)
        window_width = int(screen.width() * 0.8)
        window_height = int(screen.height() * 0.8)
        
        # Set window geometry
        self.setGeometry(
            int(screen.width() * 0.1),  # 10% from left
            int(screen.height() * 0.1),  # 10% from top
            window_width,
            window_height
        )
        
        # Set minimum size (40% of screen size)
        self.setMinimumSize(
            int(screen.width() * 0.4),
            int(screen.height() * 0.4)
        )
        
        # Main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # Template selection
        template_group = QGroupBox("Selección de Plantilla PDF")
        template_layout = QHBoxLayout()
        
        self.template_path_label = QLabel("No se ha seleccionado plantilla")
        template_select_btn = QPushButton("Seleccionar Plantilla PDF")
        template_select_btn.clicked.connect(self.select_template)
        
        set_area_btn = QPushButton("Definir Área de Trabajo")
        set_area_btn.clicked.connect(self.set_working_area)
        set_area_btn.setEnabled(False)
        self.set_area_btn = set_area_btn
        
        template_layout.addWidget(self.template_path_label)
        template_layout.addWidget(template_select_btn)
        template_layout.addWidget(set_area_btn)
        template_group.setLayout(template_layout)
        
        # PDF Preview
        preview_group = QGroupBox("Vista Previa")
        preview_layout = QVBoxLayout()
        
        self.pdf_preview = PDFPreviewWidget()
        
        # Add the preview widget to a scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.pdf_preview)
        scroll_area.setWidgetResizable(True)
        
        preview_layout.addWidget(scroll_area)
        preview_group.setLayout(preview_layout)
        
        # Form fields
        form_group = QGroupBox("Datos de la Receta")
        form_layout = QFormLayout()
        
        # Date field
        self.fecha_edit = QDateEdit()
        self.fecha_edit.setDate(QDate.currentDate())
        self.fecha_edit.setCalendarPopup(True)
        form_layout.addRow("Fecha:", self.fecha_edit)
        
        # Patient info
        self.paciente_edit = QLineEdit()
        form_layout.addRow("Paciente:", self.paciente_edit)
        
        self.edad_edit = QSpinBox()
        self.edad_edit.setRange(0, 120)
        form_layout.addRow("Edad:", self.edad_edit)
        
        # Patient characteristics
        self.biotipo_edit = QComboBox()
        self.biotipo_edit.addItems(["Normolíneo", "Brevilíneo", "Longilíneo"])
        form_layout.addRow("Biotipo:", self.biotipo_edit)
        
        self.fototipo_edit = QComboBox()
        self.fototipo_edit.addItems(["I", "II", "III", "IV", "V", "VI"])
        form_layout.addRow("Fototipo:", self.fototipo_edit)
        
        self.envejecimiento_edit = QComboBox()
        self.envejecimiento_edit.addItems(["Leve", "Moderado", "Avanzado"])
        form_layout.addRow("Grado de envejecimiento:", self.envejecimiento_edit)
        
        # Medical info
        self.diagnostico_edit = QTextEdit()
        form_layout.addRow("Diagnóstico:", self.diagnostico_edit)
        
        self.plan_tratamiento_edit = QTextEdit()
        form_layout.addRow("Plan de tratamiento:", self.plan_tratamiento_edit)
        
        self.rutina_am_edit = QTextEdit()
        form_layout.addRow("Rutina Facial (AM):", self.rutina_am_edit)
        
        self.rutina_pm_edit = QTextEdit()
        form_layout.addRow("Rutina Facial (PM):", self.rutina_pm_edit)
        
        self.recomendacion_edit = QTextEdit()
        form_layout.addRow("Recomendación Antiestres y Performance:", self.recomendacion_edit)
        
        # Next appointment
        self.proxima_cita_edit = QDateEdit()
        self.proxima_cita_edit.setDate(QDate.currentDate().addDays(30))
        self.proxima_cita_edit.setCalendarPopup(True)
        form_layout.addRow("Próxima cita médica:", self.proxima_cita_edit)
        
        # Add formatting button to each text field
        for field_name, field in [
            ('fecha', self.fecha_edit),
            ('paciente', self.paciente_edit),
            ('edad', self.edad_edit),
            ('biotipo', self.biotipo_edit),
            ('fototipo', self.fototipo_edit),
            ('envejecimiento', self.envejecimiento_edit),
            ('diagnostico', self.diagnostico_edit),
            ('plan_tratamiento', self.plan_tratamiento_edit),
            ('rutina_am', self.rutina_am_edit),
            ('rutina_pm', self.rutina_pm_edit),
            ('recomendacion', self.recomendacion_edit),
            ('proxima_cita', self.proxima_cita_edit)
        ]:
            format_btn = QPushButton("Formato")
            format_btn.clicked.connect(lambda checked, f=field_name: self.show_format_dialog(f))
            
            # Create a container for the field and its format button
            field_container = QWidget()
            field_layout = QHBoxLayout()
            field_layout.addWidget(field)
            field_layout.addWidget(format_btn)
            field_container.setLayout(field_layout)
            
            form_layout.addRow(f"{field_name.title()}:", field_container)
        
        # Store field styles
        self.field_styles = {}
        
        # Connect text change signals for live preview
        for field in [self.fecha_edit, self.paciente_edit, self.edad_edit,
                      self.biotipo_edit, self.fototipo_edit, self.envejecimiento_edit,
                      self.diagnostico_edit, self.plan_tratamiento_edit,
                      self.rutina_am_edit, self.rutina_pm_edit,
                      self.recomendacion_edit, self.proxima_cita_edit]:
            if isinstance(field, QTextEdit):
                field.textChanged.connect(self.update_preview)
            elif isinstance(field, QLineEdit):
                field.textChanged.connect(self.update_preview)
            elif isinstance(field, QDateEdit):
                field.dateChanged.connect(self.update_preview)
            elif isinstance(field, QSpinBox):
                field.valueChanged.connect(self.update_preview)
            elif isinstance(field, QComboBox):
                field.currentTextChanged.connect(self.update_preview)
        
        form_group.setLayout(form_layout)
        
        # Action buttons
        actions_layout = QHBoxLayout()
        
        generate_btn = QPushButton("Generar PDF")
        generate_btn.clicked.connect(self.generate_pdf)
        
        clear_btn = QPushButton("Limpiar Campos")
        clear_btn.clicked.connect(self.clear_fields)
        
        actions_layout.addWidget(generate_btn)
        actions_layout.addWidget(clear_btn)
        
        # Split the main layout into two columns
        content_layout = QHBoxLayout()
        
        # Left column for preview
        left_column = QVBoxLayout()
        left_column.addWidget(preview_group)
        
        # Right column for form
        right_column = QVBoxLayout()
        right_column.addWidget(form_group)
        
        # Add columns to content layout
        content_layout.addLayout(left_column, 3)  # 3:2 ratio
        content_layout.addLayout(right_column, 2)
        
        # Add all components to main layout
        main_layout.addWidget(template_group)
        main_layout.addLayout(content_layout)
        main_layout.addLayout(actions_layout)
        
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
    
    def select_template(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Plantilla PDF", "", "PDF Files (*.pdf)")
        
        if file_path:
            self.template_pdf_path = file_path
            self.template_path_label.setText(os.path.basename(file_path))
            
            # Set the template path in the preview widget
            self.pdf_preview.set_template_path(file_path)
            
            # Load the PDF for preview
            if self.pdf_preview.load_pdf(file_path):
                self.set_area_btn.setEnabled(True)
            else:
                QMessageBox.warning(self, "Error", "No se pudo cargar el PDF seleccionado.")
    
    def set_working_area(self):
        # Get the selected area from the preview widget
        selected_rect = self.pdf_preview.get_selection_rect()
        
        if selected_rect:
            self.working_area = selected_rect
            QMessageBox.information(self, "Área de Trabajo", 
                                   f"Área de trabajo definida: ({selected_rect.x()}, {selected_rect.y()}, "
                                   f"{selected_rect.width()}x{selected_rect.height()})")
        else:
            QMessageBox.warning(self, "Selección", 
                               "Por favor, seleccione un área en la vista previa usando el mouse.")
    
    def clear_fields(self):
        self.paciente_edit.clear()
        self.edad_edit.setValue(0)
        self.biotipo_edit.setCurrentIndex(0)
        self.fototipo_edit.setCurrentIndex(0)
        self.envejecimiento_edit.setCurrentIndex(0)
        self.diagnostico_edit.clear()
        self.plan_tratamiento_edit.clear()
        self.rutina_am_edit.clear()
        self.rutina_pm_edit.clear()
        self.recomendacion_edit.clear()
        self.fecha_edit.setDate(QDate.currentDate())
        self.proxima_cita_edit.setDate(QDate.currentDate().addDays(30))
    
    def generate_pdf(self):
        if not self.template_pdf_path:
            QMessageBox.warning(self, "Error", "Por favor seleccione una plantilla PDF primero.")
            return
        
        if not self.working_area:
            QMessageBox.warning(self, "Error", "Por favor defina el área de trabajo primero.")
            return
        
        try:
            # Get save location
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Guardar PDF", "", "PDF Files (*.pdf)")
            
            if not save_path:
                return
            
            # Create overlay with form data
            overlay_pdf = self.create_overlay()
            
            # Merge template with overlay
            self.pdf_preview.merge_pdfs(self.template_pdf_path, overlay_pdf, save_path)
            
            QMessageBox.information(self, "Éxito", f"PDF guardado exitosamente en:\n{save_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al generar PDF: {str(e)}")
    
    def create_overlay(self):
        # Check if working area is defined
        if not self.working_area:
            return None
        
        # Create a temporary file for the overlay
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_file.close()
        
        # Get the dimensions of the original PDF to match it exactly
        original_pdf = fitz.open(self.template_pdf_path)
        page = original_pdf[0]
        pdf_width = page.rect.width
        pdf_height = page.rect.height
        original_pdf.close()
        
        # Create a canvas with the same dimensions as the original PDF
        c = canvas.Canvas(temp_file.name, pagesize=(pdf_width, pdf_height))
        
        # Get the working area coordinates
        x_offset = self.working_area.x()
        y_offset = self.working_area.y()
        work_width = self.working_area.width()
        work_height = self.working_area.height()
        
        # In PDF coordinates, y=0 is at the bottom
        y_offset = pdf_height - y_offset - work_height
        
        # Calculate positions relative to the working area
        margin = 10  # 10 points margin
        x_pos = x_offset + margin
        y_pos = y_offset + work_height - margin
        line_height = 14  # Height for each line of text
        
        # Function to wrap text and handle page breaks
        def draw_wrapped_text(text, y_pos, style=None):
            if style:
                font_name = style['font']
                font_size = style['size']
                if style.get('bold', False):
                    font_name = f"{font_name}-Bold"
                if style.get('italic', False):
                    font_name = f"{font_name}-Italic"
                if style.get('underline', False):
                    font_name = f"{font_name}-Underline"
                c.setFont(font_name, font_size)
            else:
                c.setFont("Helvetica", 10)
                font_size = 10
            
            # Calculate available width for text
            available_width = work_width - 2 * margin
            
            # Split text into words
            words = text.split()
            current_line = []
            current_width = 0
            
            for word in words:
                # Calculate word width with current font
                word_width = c.stringWidth(word + " ", font_name, font_size)
                
                if current_width + word_width <= available_width:
                    current_line.append(word)
                    current_width += word_width
                else:
                    # Draw current line
                    if y_pos < y_offset:  # If we're below the working area
                        c.showPage()  # Create new page
                        y_pos = y_offset + work_height - margin
                    
                    c.drawString(x_pos, y_pos, " ".join(current_line))
                    y_pos -= line_height
                    current_line = [word]
                    current_width = word_width
            
            # Draw the last line
            if current_line:
                if y_pos < y_offset:
                    c.showPage()
                    y_pos = y_offset + work_height - margin
                
                c.drawString(x_pos, y_pos, " ".join(current_line))
                y_pos -= line_height
            
            return y_pos
        
        # Draw form data with formatting
        fecha = self.fecha_edit.date().toString("dd/MM/yyyy")
        y_pos = draw_wrapped_text(f"Fecha: {fecha}", y_pos, self.get_field_style('fecha'))
        
        y_pos = draw_wrapped_text(f"Paciente: {self.paciente_edit.text()}", y_pos, self.get_field_style('paciente'))
        y_pos = draw_wrapped_text(f"Edad: {self.edad_edit.value()} años", y_pos, self.get_field_style('edad'))
        y_pos = draw_wrapped_text(f"Biotipo: {self.biotipo_edit.currentText()}", y_pos, self.get_field_style('biotipo'))
        y_pos = draw_wrapped_text(f"Fototipo: {self.fototipo_edit.currentText()}", y_pos, self.get_field_style('fototipo'))
        y_pos = draw_wrapped_text(f"Grado de envejecimiento: {self.envejecimiento_edit.currentText()}", 
                                y_pos, self.get_field_style('envejecimiento'))
        
        y_pos -= line_height * 0.5
        y_pos = draw_wrapped_text("Diagnóstico:", y_pos, self.get_field_style('diagnostico_label'))
        
        for line in self.diagnostico_edit.toPlainText().split('\n'):
            y_pos = draw_wrapped_text(line, y_pos, self.get_field_style('diagnostico'))
        
        c.save()
        return temp_file.name
    
    def show_format_dialog(self, field_name):
        dialog = TextFormatDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.field_styles[field_name] = dialog.get_format()
            self.update_preview()

    def get_field_style(self, field_name):
        return self.field_styles.get(field_name, {
            'font': 'Helvetica',
            'size': 10,
            'bold': False,
            'italic': False,
            'underline': False
        })

    def update_preview(self):
        # Only update preview if we have a working area defined
        if not self.working_area:
            return
        
        try:
            # Create a temporary overlay with current content
            overlay_pdf = self.create_overlay()
            
            if overlay_pdf:
                # Update the preview with the new overlay
                self.pdf_preview.update_with_overlay(overlay_pdf)
        except Exception as e:
            print(f"Error updating preview: {e}")

class TextFormatDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("Formato de Texto")
        layout = QFormLayout()
        
        # Font selection
        self.font_combo = QFontComboBox()
        layout.addRow("Fuente:", self.font_combo)
        
        # Font size
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 72)
        self.size_spin.setValue(10)
        layout.addRow("Tamaño:", self.size_spin)
        
        # Style options
        self.bold_check = QCheckBox("Negrita")
        self.italic_check = QCheckBox("Cursiva")
        self.underline_check = QCheckBox("Subrayado")
        
        style_layout = QHBoxLayout()
        style_layout.addWidget(self.bold_check)
        style_layout.addWidget(self.italic_check)
        style_layout.addWidget(self.underline_check)
        layout.addRow("Estilo:", style_layout)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        self.setLayout(layout)
    
    def get_format(self):
        return {
            'font': self.font_combo.currentFont().family(),
            'size': self.size_spin.value(),
            'bold': self.bold_check.isChecked(),
            'italic': self.italic_check.isChecked(),
            'underline': self.underline_check.isChecked()
        }

def main():
    app = QApplication(sys.argv)
    window = MedicalRecipeEditor()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
