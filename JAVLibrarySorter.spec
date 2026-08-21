# PyInstaller spec for JAVLibrary Sorter.
#
# Build with:  pyinstaller JAVLibrarySorter.spec
# Output:      dist/JAVLibrarySorter/JAVLibrarySorter.exe
#
# onedir rather than onefile: a onefile build unpacks Qt to a temp folder
# on every launch, which makes startup noticeably slower for no benefit
# here.

a = Analysis(
    ["javsorter/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # Qt ships a lot we never touch. Dropping these keeps the build to a
    # sane size; none are imported by this app.
    excludes=[
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtBluetooth",
        "PySide6.QtDesigner",
        "tkinter",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="JAVLibrarySorter",
    debug=False,
    strip=False,
    upx=False,
    # windowed: no console window behind the GUI.
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="JAVLibrarySorter",
)
