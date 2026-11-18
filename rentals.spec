# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Rentals Manager desktop app (onedir build)."""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("templates", "templates"),
    ("static", "static"),
    ("docs", "docs"),
]
binaries = []
hiddenimports = []

for package in ("webview", "waitress", "escpos", "reportlab", "openpyxl", "PIL"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
    except Exception:
        continue
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

hiddenimports += collect_submodules("django")
hiddenimports += ["config.settings", "config.urls"]

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RentalsManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RentalsManager",
)
