from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_desktop_ui_imports_are_lazy():
    text=(ROOT/'app'/'main.py').read_text()
    assert 'from PyQt6' not in text
    assert 'from scripts.run_local_desktop import main as run_embedded_web_desktop' in text
    assert text.index('def main():') < text.index('from scripts.run_local_desktop import main')

def test_cloud_entrypoint_uses_runtime_without_desktop_ui():
    text=(ROOT/'server'/'cloud_app.py').read_text()
    assert 'from app.main import build_runtime' in text
    assert 'create_app(' in text
    assert 'PyQt6' not in text
    assert 'MainWindow' not in text
