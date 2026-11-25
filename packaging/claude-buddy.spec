# PyInstaller spec for Claude Buddy (one-folder build, windowed). Run via packaging/build.ps1.
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is injected by PyInstaller

# Qt modules the app never imports (keeps the installer small)
EXCLUDES = [
    "tkinter", "unittest", "pydoc_data",
    "PIL",                     # dev-only (README GIFs); optional imports would drag it in
    "pytest", "_pytest",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSvgWidgets", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml",
    "PySide6.QtConcurrent", "PySide6.QtDBus", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtUiTools", "PySide6.QtPrintSupport", "PySide6.QtMultimedia", "PySide6.QtWebEngineCore",
]

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    excludes=EXCLUDES,
    noarchive=False,
)

# Never ship the SDK's bundled claude.exe (~388 MB): the app uses the user's installed Claude Code
a.datas = [d for d in a.datas if "_bundled" not in d[0]]
a.binaries = [b for b in a.binaries if "_bundled" not in b[0]]
# Software OpenGL fallback (20 MB) is unused by a widgets app; keep only Spanish/English Qt translations
a.binaries = [b for b in a.binaries if not b[0].lower().endswith("opengl32sw.dll")]
a.datas = [d for d in a.datas
           if "translations" not in d[0].replace("\\", "/") or any(k in d[0] for k in ("_es.", "_en."))]

pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClaudeBuddy",
    console=False,
    icon=str(ROOT / "build" / "claude-buddy.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ClaudeBuddy", upx=False)  # noqa: F821
