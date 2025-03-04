import os
import sys
import tempfile
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QTextEdit, 
                            QPushButton, QFileDialog, QFormLayout, QGroupBox,
                            QDateEdit, QSpinBox, QComboBox, QMessageBox,
                            QScrollArea, QFrame, QSizePolicy, QDialog,
                            QDialogButtonBox, QFontComboBox, QCheckBox,
                            QToolBar, QToolButton)
from PyQt6.QtCore import Qt, QDate, QRect, QPoint, QSizeF, QTimer, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QPageSize, QScreen, QIcon, QFont, QAction
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
        
        # Create main layout
        main_layout = QVBoxLayout(self)
        
        # Create navigation panel with better styling
        nav_panel = QWidget()
        nav_layout = QHBoxLayout(nav_panel)
        nav_panel.setMaximumHeight(50)  # Limit height of navigation panel
        
        self.prev_page_btn = QPushButton("←")
        self.next_page_btn = QPushButton("→")
        self.page_label = QLabel("Página 1")
        
        # Style the navigation buttons
        button_style = """
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """
        self.prev_page_btn.setStyleSheet(button_style)
        self.next_page_btn.setStyleSheet(button_style)
        self.prev_page_btn.setFixedSize(40, 30)
        self.next_page_btn.setFixedSize(40, 30)
        self.page_label.setStyleSheet("QLabel { padding: 0 10px; }")
        
        self.prev_page_btn.clicked.connect(self.prev_page)
        self.next_page_btn.clicked.connect(self.next_page)
        
        nav_layout.addStretch()
        nav_layout.addWidget(self.prev_page_btn)
        nav_layout.addWidget(self.page_label)
        nav_layout.addWidget(self.next_page_btn)
        nav_layout.addStretch()
        nav_panel.setLayout(nav_layout)
        
        # Create PDF view area - this is a simple widget that will display the PDF
        self.pdf_view = QWidget()
        self.pdf_view.setMinimumSize(400, 450)
        self.pdf_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.pdf_view.setMouseTracking(True)
        
        # Set up the PDF view to handle painting and mouse events
        self.pdf_view.paintEvent = lambda e: self._paint_pdf(e)
        self.pdf_view.mousePressEvent = lambda e: self._mouse_press(e)
        self.pdf_view.mouseMoveEvent = lambda e: self._mouse_move(e)
        self.pdf_view.mouseReleaseEvent = lambda e: self._mouse_release(e)
        
        # Add widgets to main layout
        main_layout.addWidget(nav_panel)
        main_layout.addWidget(self.pdf_view)
        
        self.update_navigation()
    
    def _paint_pdf(self, event):
        painter = QPainter(self.pdf_view)
        
        # Draw white background
        painter.fillRect(event.rect(), Qt.GlobalColor.white)
        
        if self.pixmap:
            # Calculate the PDF rectangle in widget coordinates
            x = (self.pdf_view.width() - self.pixmap.width()) / 2
            y = (self.pdf_view.height() - self.pixmap.height()) / 2
            self.pdf_rect = QRect(int(x), int(y), self.pixmap.width(), self.pixmap.height())
            
            # Draw the PDF preview centered
            painter.drawPixmap(self.pdf_rect, self.pixmap)
            
            # Draw a border around the PDF
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.drawRect(self.pdf_rect)
            
            # Draw the selection rectangle if it exists
            if self.selection_rect:
                painter.setPen(QPen(QColor(255, 0, 0), 2, Qt.PenStyle.DashLine))
                painter.drawRect(self.selection_rect)
    
    def _mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.pdf_rect:
            # Check if click is inside the PDF area
            if self.pdf_rect.contains(event.position().toPoint()):
                # Start selection
                self.is_selecting = True
                self.start_point = event.position().toPoint()
                self.end_point = self.start_point
                self.selection_rect = QRect(self.start_point, self.end_point)
                self.pdf_view.update()
    
    def _mouse_move(self, event):
        if self.is_selecting and self.pdf_rect:
            # Update end point, but constrain to PDF area
            current_pos = event.position().toPoint()
            
            # Constrain to PDF boundaries
            x = max(self.pdf_rect.left(), min(current_pos.x(), self.pdf_rect.right()))
            y = max(self.pdf_rect.top(), min(current_pos.y(), self.pdf_rect.bottom()))
            
            self.end_point = QPoint(x, y)
            
            # Update selection rectangle
            self.selection_rect = QRect(self.start_point, self.end_point).normalized()
            self.pdf_view.update()
    
    def _mouse_release(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.is_selecting = False
            
            # Finalize selection rectangle
            if self.start_point and self.end_point:
                self.selection_rect = QRect(self.start_point, self.end_point).normalized()
                
                # If the selection is too small, ignore it
                if self.selection_rect.width() < 10 or self.selection_rect.height() < 10:
                    self.selection_rect = None
                
                self.pdf_view.update()
    
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
                width_scale = (self.pdf_view.width() - 40) / page_width  # 20px margin on each side
                height_scale = (self.pdf_view.height() - 40) / page_height  # 20px margin on each side
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
            x = (self.pdf_view.width() - self.pixmap.width()) / 2
            y = (self.pdf_view.height() - self.pixmap.height()) / 2
            self.pdf_rect = QRect(int(x), int(y), self.pixmap.width(), self.pixmap.height())
            
            # Reset selection when loading a new PDF
            self.selection_rect = None
            self.start_point = None
            self.end_point = None
            
            # Update the widget
            self.pdf_view.update()
            
        except Exception as e:
            print(f"Error updating preview: {e}")
    
    def resizeEvent(self, event):
        # Recalculate PDF position when widget is resized
        if self.pixmap:
            x = (self.width() - self.pixmap.width()) / 2
            y = (self.height() - self.pixmap.height()) / 2
            self.pdf_rect = QRect(int(x), int(y), self.pixmap.width(), self.pixmap.height())
        super().resizeEvent(event)
    
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
            
            # Update navigation buttons - make sure this happens after loading the PDF
            self.update_navigation()
            
            # Force a repaint
            self.pdf_view.update()
            
        except Exception as e:
            print(f"Error updating preview: {e}")

    def set_template_path(self, path):
        self.template_pdf_path = path

    def merge_pdfs(self, template_path, overlay_path, output_path):
        # Read the template PDF
        template_pdf = PdfReader(template_path)
        overlay_pdf = PdfReader(overlay_path)
        output = PdfWriter()
        
        # Get the number of pages needed
        num_pages = max(len(template_pdf.pages), len(overlay_pdf.pages))
        
        # For each page
        for i in range(num_pages):
            # If we need more template pages, copy the first page
            if i < len(template_pdf.pages):
                # Use the existing template page
                template_page = template_pdf.pages[i]
            else:
                # Create a clean copy of the first page for additional pages
                # This ensures we only get the background, not any content
                template_page = PdfReader(template_path).pages[0]
            
            # If we have an overlay page, merge it
            if i < len(overlay_pdf.pages):
                # Merge the overlay content onto the template
                template_page.merge_page(overlay_pdf.pages[i])
            
            output.add_page(template_page)
        
        # Write the output PDF
        with open(output_path, 'wb') as output_file:
            output.write(output_file)

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_preview()
            self.update_navigation()
    
    def next_page(self):
        if self.pdf_document and self.current_page < len(self.pdf_document) - 1:
            self.current_page += 1
            self.update_preview()
            self.update_navigation()
    
    def update_navigation(self):
        if self.pdf_document:
            total_pages = len(self.pdf_document)
            self.page_label.setText(f"Página {self.current_page + 1} de {total_pages}")
            self.prev_page_btn.setEnabled(self.current_page > 0)
            self.next_page_btn.setEnabled(self.current_page < total_pages - 1)
        else:
            self.page_label.setText("Sin documento")
            self.prev_page_btn.setEnabled(False)
            self.next_page_btn.setEnabled(False)

    def create_overlay(self):
        if not self.pdf_document:
            return None
        
        try:
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
            
            # Function to create a new page with the same template
            def create_new_page():
                c.showPage()
                # Set up the new page with the same dimensions
                c.setPageSize((pdf_width, pdf_height))
                # Reset the position to the top of the working area
                return y_offset + work_height - margin
            
            # Function to draw section header
            def draw_section_header(text, y_pos, style=None):
                if style:
                    c.setFont(style['font'], style['size'])
                else:
                    c.setFont("Helvetica-Bold", 12)
                c.drawString(x_pos, y_pos, text)
                return y_pos - line_height * 1.5
            
            # Function to wrap text and handle page breaks
            def draw_wrapped_text(text, y_pos, style=None, is_continuation=False):
                # Store the original style to reapply after page breaks
                original_style = style
                
                if style:
                    font_name = style['font']
                    font_size = style['size']
                    
                    # Check if the font is available in ReportLab's standard fonts
                    standard_fonts = ['Helvetica', 'Times-Roman', 'Courier', 'Symbol', 'ZapfDingbats']
                    
                    # If the font is not a standard font, fall back to Helvetica
                    if font_name not in standard_fonts:
                        font_name = 'Helvetica'
                        
                    # Apply styling
                    if style.get('bold', False):
                        if font_name in ['Helvetica', 'Times-Roman', 'Courier']:
                            font_name = f"{font_name}-Bold"
                    if style.get('italic', False):
                        if font_name in ['Helvetica', 'Times-Roman', 'Courier']:
                            font_name = f"{font_name}-Oblique" if font_name == 'Helvetica' else f"{font_name}-Italic"
                        
                    # Note: ReportLab doesn't support underline directly in font names
                    # We'll handle underline separately if needed
                        
                    c.setFont(font_name, font_size)
                else:
                    font_name = "Helvetica"
                    font_size = self.DEFAULT_FONT_SIZE
                    c.setFont(font_name, font_size)
                
                # Calculate available width for text
                available_width = work_width - 2 * margin
                
                # Split text into words
                words = text.split()
                current_line = []
                current_width = 0
                
                for word in words:
                    word_width = c.stringWidth(word + " ", font_name, font_size)
                    
                    if current_width + word_width <= available_width:
                        current_line.append(word)
                        current_width += word_width
                    else:
                        # Check if we need a new page
                        if y_pos - line_height < y_offset:
                            y_pos = create_new_page()
                            # Reapply the original style after page break
                            if original_style:
                                font_name = original_style['font']
                                font_size = original_style['size']
                                if original_style.get('bold', False):
                                    font_name = f"{font_name}-Bold"
                                if original_style.get('italic', False):
                                    font_name = f"{font_name}-Italic"
                                if original_style.get('underline', False):
                                    font_name = f"{font_name}-Underline"
                                c.setFont(font_name, font_size)
                            
                        # Draw current line
                        c.drawString(x_pos, y_pos, " ".join(current_line))
                        y_pos -= line_height
                        current_line = [word]
                        current_width = word_width
                
                # Draw the last line
                if current_line:
                    if y_pos - line_height < y_offset:
                        y_pos = create_new_page()
                        # Reapply the original style after page break
                        if original_style:
                            font_name = original_style['font']
                            font_size = original_style['size']
                            if original_style.get('bold', False):
                                font_name = f"{font_name}-Bold"
                            if original_style.get('italic', False):
                                font_name = f"{font_name}-Italic"
                            if original_style.get('underline', False):
                                font_name = f"{font_name}-Underline"
                            c.setFont(font_name, font_size)
                        
                    c.drawString(x_pos, y_pos, " ".join(current_line))
                    y_pos -= line_height
                
                return y_pos
            
            # Draw form data with formatting - make labels bold but content regular
            fecha = self.format_date_spanish(self.fecha_edit.date())
            # For each field, split the label and content
            fecha_label_style = self.get_field_style('fecha_label')
            fecha_content_style = self.get_field_style('fecha')
            c.setFont(fecha_label_style['font'] + ("-Bold" if fecha_label_style.get('bold', True) else ""), fecha_label_style['size'])
            c.drawString(x_pos, y_pos, "Fecha: ")
            label_width = c.stringWidth("Fecha: ", fecha_label_style['font'] + ("-Bold" if fecha_label_style.get('bold', True) else ""), fecha_label_style['size'])
            c.setFont(fecha_content_style['font'] + ("-Bold" if fecha_content_style.get('bold', False) else ""), fecha_content_style['size'])
            c.drawString(x_pos + label_width, y_pos, fecha)
            y_pos -= line_height
            
            # Apply the same pattern for other basic fields
            fields = [
                ("Paciente: ", self.paciente_edit.text(), 'paciente_label', 'paciente'),
                (f"Edad: ", f"{self.edad_edit.value()} años", 'edad_label', 'edad'),
                ("Biotipo: ", self.biotipo_edit.currentText(), 'biotipo_label', 'biotipo'),
                ("Fototipo: ", self.fototipo_edit.currentText(), 'fototipo_label', 'fototipo'),
                ("Grado de envejecimiento: ", self.envejecimiento_edit.currentText(), 'envejecimiento_label', 'envejecimiento')
            ]
            
            for label_text, content_text, label_style_name, content_style_name in fields:
                label_style = self.get_field_style(label_style_name)
                content_style = self.get_field_style(content_style_name)
                
                c.setFont(label_style['font'] + ("-Bold" if label_style.get('bold', True) else ""), label_style['size'])
                c.drawString(x_pos, y_pos, label_text)
                label_width = c.stringWidth(label_text, label_style['font'] + ("-Bold" if label_style.get('bold', True) else ""), label_style['size'])
                
                c.setFont(content_style['font'] + ("-Bold" if content_style.get('bold', False) else ""), content_style['size'])
                c.drawString(x_pos + label_width, y_pos, content_text)
                y_pos -= line_height
            
            y_pos -= line_height * 0.5
            y_pos = draw_wrapped_text("Diagnóstico:", y_pos, self.get_field_style('diagnostico_label'))
            
            for line in self.diagnostico_edit.toPlainText().split('\n'):
                if line.strip():  # Only process non-empty lines
                    y_pos = draw_wrapped_text(line, y_pos, self.get_field_style('diagnostico'))
            
            y_pos -= line_height * 0.5
            y_pos = draw_wrapped_text("Plan de tratamiento:", y_pos, self.get_field_style('plan_tratamiento_label'))
            
            for line in self.plan_tratamiento_edit.toPlainText().split('\n'):
                if line.strip():  # Only process non-empty lines
                    y_pos = draw_wrapped_text(line, y_pos, self.get_field_style('plan_tratamiento'))
            
            y_pos -= line_height * 0.5
            y_pos = draw_wrapped_text("Rutina Facial (AM):", y_pos, self.get_field_style('rutina_am_label'))
            
            for line in self.rutina_am_edit.toPlainText().split('\n'):
                if line.strip():  # Only process non-empty lines
                    y_pos = draw_wrapped_text(line, y_pos, self.get_field_style('rutina_am'))
            
            y_pos -= line_height * 0.5
            y_pos = draw_wrapped_text("Rutina Facial (PM):", y_pos, self.get_field_style('rutina_pm_label'))
            
            for line in self.rutina_pm_edit.toPlainText().split('\n'):
                if line.strip():  # Only process non-empty lines
                    y_pos = draw_wrapped_text(line, y_pos, self.get_field_style('rutina_pm'))
            
            y_pos -= line_height * 0.5
            y_pos = draw_wrapped_text("Recomendación Antiestres y Performance:", y_pos, self.get_field_style('recomendacion_label'))
            
            for line in self.recomendacion_edit.toPlainText().split('\n'):
                if line.strip():  # Only process non-empty lines
                    y_pos = draw_wrapped_text(line, y_pos, self.get_field_style('recomendacion'))
            
            y_pos -= line_height * 0.5
            proxima_cita = self.proxima_cita_edit.date().toString("dd/MM/yyyy")
            y_pos = draw_wrapped_text(f"Próxima cita médica: {proxima_cita}", y_pos, self.get_field_style('proxima_cita'))
            
            c.save()
            return temp_file.name
        except Exception as e:
            print(f"Error creating overlay: {e}")
            return None

    def format_date_spanish(self, qdate):
        """Format date in Spanish: 'Riobamba, 4 de marzo de 2025'"""
        day = qdate.day()
        month = qdate.month()
        year = qdate.year()
        
        # Spanish month names
        months = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }
        
        # Format the date
        return f"Riobamba, {day} de {months[month]} de {year}"

    def get_field_style(self, field_name):
        # Adjust the DEFAULT_FONT_SIZE to appear correctly in the PDF
        # PDF points are typically 1/72 inch, so we might need to adjust
        adjusted_size = self.DEFAULT_FONT_SIZE * 0.9  # Slightly reduce size to match visual expectations
        
        # Default styles based on field type
        if field_name.endswith('_label'):
            # All labels (section headers and field labels) should be consistent
            return self.field_styles.get(field_name, {
                'font': 'Helvetica',
                'size': adjusted_size,
                'bold': True,  # All labels are bold
                'italic': False,
                'underline': False
            })
        elif field_name in ['fecha', 'paciente', 'edad', 'biotipo', 'fototipo', 'envejecimiento', 'proxima_cita']:
            # Basic info fields content (not bold)
            return self.field_styles.get(field_name, {
                'font': 'Helvetica',
                'size': adjusted_size,
                'bold': False,  # Content is not bold
                'italic': False,
                'underline': False
            })
        else:
            # Content fields (diagnostico, plan_tratamiento, etc.)
            return self.field_styles.get(field_name, {
                'font': 'Helvetica',
                'size': adjusted_size,
                'bold': False,
                'italic': False,
                'underline': False
            })

class MedicalRecipeEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.template_pdf_path = None
        self.working_area = None
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._do_update_preview)
        
        # Global font size setting
        self.DEFAULT_FONT_SIZE = 9
        
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
        form_layout.setSpacing(10)  # Add more spacing between form rows
        
        # Create a function to add a field with formatting toolbar
        def add_field_with_formatting(label, field, field_name):
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)
            
            # Add the field
            layout.addWidget(field)
            
            # Create formatting toolbar
            toolbar = QToolBar()
            toolbar.setIconSize(QSize(16, 16))
            toolbar.setStyleSheet("""
                QToolBar {
                    background-color: #f5f5f5;
                    border: 1px solid #ddd;
                    border-radius: 3px;
                    padding: 2px;
                }
                QToolButton {
                    border: none;
                    padding: 3px;
                    border-radius: 2px;
                }
                QToolButton:hover {
                    background-color: #e0e0e0;
                }
                QToolButton:checked {
                    background-color: #d0d0d0;
                }
            """)
            
            # Only add font controls for text fields
            if isinstance(field, QTextEdit) or isinstance(field, QLineEdit):
                font_combo = QFontComboBox()
                font_combo.clear()  # Clear all fonts
                
                # Add only the fonts that ReportLab supports by default
                reportlab_fonts = ['Helvetica', 'Times-Roman', 'Courier']
                for font in reportlab_fonts:
                    font_combo.addItem(font)
                
                font_combo.setCurrentText("Helvetica")
                font_combo.setMaximumWidth(150)
                font_combo.currentTextChanged.connect(  # Use currentTextChanged instead of currentFontChanged
                    lambda text: self.apply_format(field_name, 'font', text))
                toolbar.addWidget(font_combo)
                
                # Font size selector
                size_spin = QSpinBox()
                size_spin.setRange(8, 24)
                size_spin.setValue(self.DEFAULT_FONT_SIZE)
                size_spin.setMaximumWidth(50)
                size_spin.valueChanged.connect(
                    lambda size: self.apply_format(field_name, 'size', size))
                toolbar.addWidget(size_spin)
                
                # Add separator
                toolbar.addSeparator()
            
            # Bold button
            bold_action = QAction("B", toolbar)
            bold_action.setCheckable(True)
            bold_action.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
            bold_action.triggered.connect(
                lambda checked: self.apply_format(field_name, 'bold', checked))
            toolbar.addAction(bold_action)
            
            # Italic button
            italic_action = QAction("I", toolbar)
            italic_action.setCheckable(True)
            italic_action.setFont(QFont("Helvetica", 9, QFont.Weight.Normal, True))
            italic_action.triggered.connect(
                lambda checked: self.apply_format(field_name, 'italic', checked))
            toolbar.addAction(italic_action)
            
            # Underline button
            underline_action = QAction("U", toolbar)
            underline_action.setCheckable(True)
            font = QFont("Helvetica", 9)
            font.setUnderline(True)
            underline_action.setFont(font)
            underline_action.triggered.connect(
                lambda checked: self.apply_format(field_name, 'underline', checked))
            toolbar.addAction(underline_action)
            
            # Add toolbar to layout
            layout.addWidget(toolbar)
            
            # Add to form layout
            form_layout.addRow(label, container)
            
            # Store the formatting controls for later access
            self.formatting_controls[field_name] = {
                'bold': bold_action,
                'italic': italic_action,
                'underline': underline_action
            }
            
            if isinstance(field, QTextEdit) or isinstance(field, QLineEdit):
                self.formatting_controls[field_name]['font_combo'] = font_combo
                self.formatting_controls[field_name]['size_spin'] = size_spin
        
        # Initialize formatting controls dictionary
        self.formatting_controls = {}
        
        # Date field
        self.fecha_edit = QDateEdit()
        self.fecha_edit.setDate(QDate.currentDate())
        self.fecha_edit.setCalendarPopup(True)
        add_field_with_formatting("Fecha:", self.fecha_edit, 'fecha')
        
        # Patient info
        self.paciente_edit = QLineEdit()
        add_field_with_formatting("Paciente:", self.paciente_edit, 'paciente')
        
        self.edad_edit = QSpinBox()
        self.edad_edit.setRange(0, 120)
        add_field_with_formatting("Edad:", self.edad_edit, 'edad')
        
        # Patient characteristics
        self.biotipo_edit = QComboBox()
        self.biotipo_edit.addItems(["Normolíneo", "Brevilíneo", "Longilíneo"])
        add_field_with_formatting("Biotipo:", self.biotipo_edit, 'biotipo')
        
        self.fototipo_edit = QComboBox()
        self.fototipo_edit.addItems(["I", "II", "III", "IV", "V", "VI"])
        add_field_with_formatting("Fototipo:", self.fototipo_edit, 'fototipo')
        
        self.envejecimiento_edit = QComboBox()
        self.envejecimiento_edit.addItems(["Leve", "Moderado", "Avanzado"])
        add_field_with_formatting("Grado de envejecimiento:", self.envejecimiento_edit, 'envejecimiento')
        
        # Medical info - make text fields bigger
        self.diagnostico_edit = QTextEdit()
        self.diagnostico_edit.setMinimumHeight(120)  # Taller text area
        add_field_with_formatting("Diagnóstico:", self.diagnostico_edit, 'diagnostico')
        
        self.plan_tratamiento_edit = QTextEdit()
        self.plan_tratamiento_edit.setMinimumHeight(120)
        add_field_with_formatting("Plan de tratamiento:", self.plan_tratamiento_edit, 'plan_tratamiento')
        
        self.rutina_am_edit = QTextEdit()
        self.rutina_am_edit.setMinimumHeight(120)
        add_field_with_formatting("Rutina Facial (AM):", self.rutina_am_edit, 'rutina_am')
        
        self.rutina_pm_edit = QTextEdit()
        self.rutina_pm_edit.setMinimumHeight(120)
        add_field_with_formatting("Rutina Facial (PM):", self.rutina_pm_edit, 'rutina_pm')
        
        self.recomendacion_edit = QTextEdit()
        self.recomendacion_edit.setMinimumHeight(120)
        add_field_with_formatting("Recomendación Antiestres y Performance:", self.recomendacion_edit, 'recomendacion')
        
        # Next appointment
        self.proxima_cita_edit = QDateEdit()
        self.proxima_cita_edit.setDate(QDate.currentDate().addDays(30))
        self.proxima_cita_edit.setCalendarPopup(True)
        add_field_with_formatting("Próxima cita médica:", self.proxima_cita_edit, 'proxima_cita')
        
        # Store field styles
        self.field_styles = {}
        
        # Add default styles for field labels
        self.field_styles = {
            'fecha_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True},
            'paciente_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True},
            'edad_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True},
            'biotipo_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True},
            'fototipo_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True},
            'envejecimiento_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True},
            'diagnostico_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True},
            'plan_tratamiento_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True},
            'rutina_am_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True},
            'rutina_pm_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True},
            'recomendacion_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True},
            'proxima_cita_label': {'font': 'Helvetica', 'size': self.DEFAULT_FONT_SIZE, 'bold': True}
        }
        
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
        
        # Function to create a new page with the same template
        def create_new_page():
            c.showPage()
            # Set up the new page with the same dimensions
            c.setPageSize((pdf_width, pdf_height))
            # Reset the position to the top of the working area
            return y_offset + work_height - margin
        
        # Function to draw section header
        def draw_section_header(text, y_pos, style=None):
            if style:
                c.setFont(style['font'], style['size'])
            else:
                c.setFont("Helvetica-Bold", 12)
            c.drawString(x_pos, y_pos, text)
            return y_pos - line_height * 1.5
        
        # Function to wrap text and handle page breaks
        def draw_wrapped_text(text, y_pos, style=None, is_continuation=False):
            # Store the original style to reapply after page breaks
            original_style = style
            
            if style:
                font_name = style['font']
                font_size = style['size']
                
                # Check if the font is available in ReportLab's standard fonts
                standard_fonts = ['Helvetica', 'Times-Roman', 'Courier', 'Symbol', 'ZapfDingbats']
                
                # If the font is not a standard font, fall back to Helvetica
                if font_name not in standard_fonts:
                    font_name = 'Helvetica'
                    
                # Apply styling
                if style.get('bold', False):
                    if font_name in ['Helvetica', 'Times-Roman', 'Courier']:
                        font_name = f"{font_name}-Bold"
                if style.get('italic', False):
                    if font_name in ['Helvetica', 'Times-Roman', 'Courier']:
                        font_name = f"{font_name}-Oblique" if font_name == 'Helvetica' else f"{font_name}-Italic"
                
                # Note: ReportLab doesn't support underline directly in font names
                # We'll handle underline separately if needed
                
                c.setFont(font_name, font_size)
            else:
                font_name = "Helvetica"
                font_size = self.DEFAULT_FONT_SIZE
                c.setFont(font_name, font_size)
            
            # Calculate available width for text
            available_width = work_width - 2 * margin
            
            # Split text into words
            words = text.split()
            current_line = []
            current_width = 0
            
            for word in words:
                word_width = c.stringWidth(word + " ", font_name, font_size)
                
                if current_width + word_width <= available_width:
                    current_line.append(word)
                    current_width += word_width
                else:
                    # Check if we need a new page
                    if y_pos - line_height < y_offset:
                        y_pos = create_new_page()
                        # Reapply the original style after page break
                        if original_style:
                            font_name = original_style['font']
                            font_size = original_style['size']
                            if original_style.get('bold', False):
                                font_name = f"{font_name}-Bold"
                            if original_style.get('italic', False):
                                font_name = f"{font_name}-Italic"
                            if original_style.get('underline', False):
                                font_name = f"{font_name}-Underline"
                            c.setFont(font_name, font_size)
                        
                    # Draw current line
                    c.drawString(x_pos, y_pos, " ".join(current_line))
                    y_pos -= line_height
                    current_line = [word]
                    current_width = word_width
            
            # Draw the last line
            if current_line:
                if y_pos - line_height < y_offset:
                    y_pos = create_new_page()
                    # Reapply the original style after page break
                    if original_style:
                        font_name = original_style['font']
                        font_size = original_style['size']
                        if original_style.get('bold', False):
                            font_name = f"{font_name}-Bold"
                        if original_style.get('italic', False):
                            font_name = f"{font_name}-Italic"
                        if original_style.get('underline', False):
                            font_name = f"{font_name}-Underline"
                        c.setFont(font_name, font_size)
                    
                
                c.drawString(x_pos, y_pos, " ".join(current_line))
                y_pos -= line_height
            
            return y_pos
        
        # Draw form data with formatting - make labels bold but content regular
        fecha = self.format_date_spanish(self.fecha_edit.date())
        # For each field, split the label and content
        fecha_label_style = self.get_field_style('fecha_label')
        fecha_content_style = self.get_field_style('fecha')
        c.setFont(fecha_label_style['font'] + ("-Bold" if fecha_label_style.get('bold', True) else ""), fecha_label_style['size'])
        c.drawString(x_pos, y_pos, "Fecha: ")
        label_width = c.stringWidth("Fecha: ", fecha_label_style['font'] + ("-Bold" if fecha_label_style.get('bold', True) else ""), fecha_label_style['size'])
        c.setFont(fecha_content_style['font'] + ("-Bold" if fecha_content_style.get('bold', False) else ""), fecha_content_style['size'])
        c.drawString(x_pos + label_width, y_pos, fecha)
        y_pos -= line_height
        
        # Apply the same pattern for other basic fields
        fields = [
            ("Paciente: ", self.paciente_edit.text(), 'paciente_label', 'paciente'),
            (f"Edad: ", f"{self.edad_edit.value()} años", 'edad_label', 'edad'),
            ("Biotipo: ", self.biotipo_edit.currentText(), 'biotipo_label', 'biotipo'),
            ("Fototipo: ", self.fototipo_edit.currentText(), 'fototipo_label', 'fototipo'),
            ("Grado de envejecimiento: ", self.envejecimiento_edit.currentText(), 'envejecimiento_label', 'envejecimiento')
        ]
        
        for label_text, content_text, label_style_name, content_style_name in fields:
            label_style = self.get_field_style(label_style_name)
            content_style = self.get_field_style(content_style_name)
            
            c.setFont(label_style['font'] + ("-Bold" if label_style.get('bold', True) else ""), label_style['size'])
            c.drawString(x_pos, y_pos, label_text)
            label_width = c.stringWidth(label_text, label_style['font'] + ("-Bold" if label_style.get('bold', True) else ""), label_style['size'])
            
            c.setFont(content_style['font'] + ("-Bold" if content_style.get('bold', False) else ""), content_style['size'])
            c.drawString(x_pos + label_width, y_pos, content_text)
            y_pos -= line_height
        
        y_pos -= line_height * 0.5
        y_pos = draw_wrapped_text("Diagnóstico:", y_pos, self.get_field_style('diagnostico_label'))
        
        for line in self.diagnostico_edit.toPlainText().split('\n'):
            if line.strip():  # Only process non-empty lines
                y_pos = draw_wrapped_text(line, y_pos, self.get_field_style('diagnostico'))
        
        y_pos -= line_height * 0.5
        y_pos = draw_wrapped_text("Plan de tratamiento:", y_pos, self.get_field_style('plan_tratamiento_label'))
        
        for line in self.plan_tratamiento_edit.toPlainText().split('\n'):
            if line.strip():  # Only process non-empty lines
                y_pos = draw_wrapped_text(line, y_pos, self.get_field_style('plan_tratamiento'))
        
        y_pos -= line_height * 0.5
        y_pos = draw_wrapped_text("Rutina Facial (AM):", y_pos, self.get_field_style('rutina_am_label'))
        
        for line in self.rutina_am_edit.toPlainText().split('\n'):
            if line.strip():  # Only process non-empty lines
                y_pos = draw_wrapped_text(line, y_pos, self.get_field_style('rutina_am'))
        
        y_pos -= line_height * 0.5
        y_pos = draw_wrapped_text("Rutina Facial (PM):", y_pos, self.get_field_style('rutina_pm_label'))
        
        for line in self.rutina_pm_edit.toPlainText().split('\n'):
            if line.strip():  # Only process non-empty lines
                y_pos = draw_wrapped_text(line, y_pos, self.get_field_style('rutina_pm'))
        
        y_pos -= line_height * 0.5
        y_pos = draw_wrapped_text("Recomendación Antiestres y Performance:", y_pos, self.get_field_style('recomendacion_label'))
        
        for line in self.recomendacion_edit.toPlainText().split('\n'):
            if line.strip():  # Only process non-empty lines
                y_pos = draw_wrapped_text(line, y_pos, self.get_field_style('recomendacion'))
        
        y_pos -= line_height * 0.5
        proxima_cita = self.proxima_cita_edit.date().toString("dd/MM/yyyy")
        y_pos = draw_wrapped_text(f"Próxima cita médica: {proxima_cita}", y_pos, self.get_field_style('proxima_cita'))
        
        c.save()
        return temp_file.name
    
    def apply_format(self, field_name, format_type, value):
        # Get or create style for this field
        if field_name not in self.field_styles:
            self.field_styles[field_name] = self.get_field_style(field_name)
        
        # Update the style
        if format_type == 'font':
            # Check if the font is available in ReportLab's standard fonts
            standard_fonts = ['Helvetica', 'Times-Roman', 'Courier', 'Symbol', 'ZapfDingbats']
            
            # If user selects a non-standard font, show a warning but still store their preference
            if value not in standard_fonts:
                print(f"Warning: Font '{value}' may not be available in PDF. Using Helvetica as fallback.")
        
        self.field_styles[field_name][format_type] = value
        
        # Update preview
        self.update_preview()
    
    def get_field_style(self, field_name):
        # Adjust the DEFAULT_FONT_SIZE to appear correctly in the PDF
        # PDF points are typically 1/72 inch, so we might need to adjust
        adjusted_size = self.DEFAULT_FONT_SIZE * 0.9  # Slightly reduce size to match visual expectations
        
        # Default styles based on field type
        if field_name.endswith('_label'):
            # All labels (section headers and field labels) should be consistent
            return self.field_styles.get(field_name, {
                'font': 'Helvetica',
                'size': adjusted_size,
                'bold': True,  # All labels are bold
                'italic': False,
                'underline': False
            })
        elif field_name in ['fecha', 'paciente', 'edad', 'biotipo', 'fototipo', 'envejecimiento', 'proxima_cita']:
            # Basic info fields content (not bold)
            return self.field_styles.get(field_name, {
                'font': 'Helvetica',
                'size': adjusted_size,
                'bold': False,  # Content is not bold
                'italic': False,
                'underline': False
            })
        else:
            # Content fields (diagnostico, plan_tratamiento, etc.)
            return self.field_styles.get(field_name, {
                'font': 'Helvetica',
                'size': adjusted_size,
                'bold': False,
                'italic': False,
                'underline': False
            })

    def update_preview(self):
        # Reset the timer
        self.preview_timer.stop()
        # Start the timer (500ms delay)
        self.preview_timer.start(500)
    
    def _do_update_preview(self):
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

    def format_date_spanish(self, qdate):
        """Format date in Spanish: 'Riobamba, 4 de marzo de 2025'"""
        day = qdate.day()
        month = qdate.month()
        year = qdate.year()
        
        # Spanish month names
        months = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }
        
        # Format the date
        return f"Riobamba, {day} de {months[month]} de {year}"

def main():
    app = QApplication(sys.argv)
    window = MedicalRecipeEditor()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()

