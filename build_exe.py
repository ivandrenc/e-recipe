import PyInstaller.__main__
import sys
import os

# Get the directory containing the script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Define the icon path (you'll need to create or provide an icon)
icon_path = os.path.join(script_dir, 'app_icon.ico')

# Fix the data file path separator based on the operating system
separator = ';' if sys.platform.startswith('win') else ':'
data_file = f'entry_manager.py{separator}.'

PyInstaller.__main__.run([
    'html2pdf.py',  # Your main script
    '--name=Medical_Recipe_Editor',  # Name of the executable (avoid spaces)
    '--onefile',  # Create a single executable file
    '--windowed',  # Don't show console window
    f'--add-data={data_file}',  # Include entry_manager.py
    '--icon=' + icon_path if os.path.exists(icon_path) else '',  # Add icon if exists
    '--clean',  # Clean PyInstaller cache
    '--noconfirm',  # Replace existing spec file
]) 