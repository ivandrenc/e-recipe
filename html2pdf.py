import os
import sys
import tempfile
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QTextEdit, 
                            QPushButton, QFileDialog, QFormLayout, QGroupBox,
                            QDateEdit, QSpinBox, QComboBox, QMessageBox,
                            QScrollArea, QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, QDate, QRect, QPoint, QSizeF
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QPageSize
from PyQt6.QtPrintSupport import QPrinter

# Since PyQt6-PDF doesn't exist, let's use an alternative approach
# We'll use fitz (PyMuPDF) for PDF rendering
import fitz  # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from PyPDF2 import PdfReader, PdfWriter

class PDFPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_document = None
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

class MedicalRecipeEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.template_pdf_path = None
        self.working_area = None
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle('Editor de Recetas Médicas')
        self.setGeometry(100, 100, 1000, 800)
        
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
            self.merge_pdfs(self.template_pdf_path, overlay_pdf, save_path)
            
            QMessageBox.information(self, "Éxito", f"PDF guardado exitosamente en:\n{save_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al generar PDF: {str(e)}")
    
    def create_overlay(self):
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
        
        # Set font and size
        c.setFont("Helvetica", 10)
        
        # Get the working area coordinates
        x_offset = self.working_area.x()
        y_offset = self.working_area.y()
        work_width = self.working_area.width()
        work_height = self.working_area.height()
        
        # In PDF coordinates, y=0 is at the bottom, but in our selection y=0 is at the top
        # So we need to flip the y-coordinate
        y_offset = pdf_height - y_offset - work_height
        
        # Calculate positions relative to the working area
        # We'll use a margin within the working area
        margin = 10  # 10 points margin
        x_pos = x_offset + margin
        y_pos = y_offset + work_height - margin  # Start from top of working area
        line_height = 14  # Height for each line of text
        
        # Draw form data
        # Format date
        fecha = self.fecha_edit.date().toString("dd/MM/yyyy")
        c.drawString(x_pos, y_pos, f"Fecha: {fecha}")
        y_pos -= line_height
        
        c.drawString(x_pos, y_pos, f"Paciente: {self.paciente_edit.text()}")
        y_pos -= line_height
        
        c.drawString(x_pos, y_pos, f"Edad: {self.edad_edit.value()} años")
        y_pos -= line_height
        
        c.drawString(x_pos, y_pos, f"Biotipo: {self.biotipo_edit.currentText()}")
        y_pos -= line_height
        
        c.drawString(x_pos, y_pos, f"Fototipo: {self.fototipo_edit.currentText()}")
        y_pos -= line_height
        
        c.drawString(x_pos, y_pos, f"Grado de envejecimiento: {self.envejecimiento_edit.currentText()}")
        y_pos -= line_height * 1.5
        
        # Multiline text fields
        c.drawString(x_pos, y_pos, "Diagnóstico:")
        y_pos -= line_height
        
        diagnostico_lines = self.diagnostico_edit.toPlainText().split('\n')
        for line in diagnostico_lines:
            c.drawString(x_pos + 10, y_pos, line)
            y_pos -= line_height
        
        y_pos -= line_height * 0.5
        c.drawString(x_pos, y_pos, "Plan de tratamiento:")
        y_pos -= line_height
        
        plan_lines = self.plan_tratamiento_edit.toPlainText().split('\n')
        for line in plan_lines:
            c.drawString(x_pos + 10, y_pos, line)
            y_pos -= line_height
        
        y_pos -= line_height * 0.5
        c.drawString(x_pos, y_pos, "Rutina Facial AM:")
        y_pos -= line_height
        
        am_lines = self.rutina_am_edit.toPlainText().split('\n')
        for line in am_lines:
            c.drawString(x_pos + 10, y_pos, line)
            y_pos -= line_height
        
        y_pos -= line_height * 0.5
        c.drawString(x_pos, y_pos, "Rutina Facial PM:")
        y_pos -= line_height
        
        pm_lines = self.rutina_pm_edit.toPlainText().split('\n')
        for line in pm_lines:
            c.drawString(x_pos + 10, y_pos, line)
            y_pos -= line_height
        
        y_pos -= line_height * 0.5
        c.drawString(x_pos, y_pos, "Recomendación Antiestres y Performance:")
        y_pos -= line_height
        
        recom_lines = self.recomendacion_edit.toPlainText().split('\n')
        for line in recom_lines:
            c.drawString(x_pos + 10, y_pos, line)
            y_pos -= line_height
        
        y_pos -= line_height * 0.5
        proxima_cita = self.proxima_cita_edit.date().toString("dd/MM/yyyy")
        c.drawString(x_pos, y_pos, f"Próxima cita médica: {proxima_cita}")
        
        # Optional: Draw a border around the working area for debugging
        # c.rect(x_offset, y_offset, work_width, work_height)
        
        c.save()
        return temp_file.name
    
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
        
        # Clean up the temporary overlay file
        os.unlink(overlay_path)

def main():
    app = QApplication(sys.argv)
    window = MedicalRecipeEditor()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
