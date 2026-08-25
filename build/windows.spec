# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

""" windows_toasts reaches its WinRT projections at call time, not through
import statements, so static analysis finds nothing to bundle: the build looks
clean, WindowsToaster() constructs fine, and the first real notification dies
with ModuleNotFoundError deep inside show_toast(). Name them all here.
collect_submodules picks up the winrt._winrt_* C extensions; the dotted
projection modules are namespace packages it does not walk, so list those. """
winrt_imports = collect_submodules('winrt') + [
    'winrt.system',
    'winrt.windows.foundation',
    'winrt.windows.foundation.collections',
    'winrt.windows.data.xml.dom',
    'winrt.windows.ui.notifications',
]

a = Analysis(
    ['../main.py'],
    pathex=[os.path.abspath(os.path.join('.', os.pardir))],
    binaries=[],
    datas=[
        ("../icons/error_icon.png",  "."),
        ("../icons/add_icon.png",    "."),
        ("../icons/delete_icon.png", "."),
        ("../icons/spinner.gif",     "."),
        ("../icons/check_icon.png",  "."),
        ("../icons/logo.png",        "."),
        ("../icons/logo.ico",        "."),
        ("../src/views/main.css",    "src/views"),
        ("../ntfy_config.json",      "."),
    ],
    hiddenimports=['windows_toasts', 'PyQt5.QtSvg', 'ntfy_notifier'] + winrt_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='cct_by_sbm',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='..\\icons\\logo.ico',
)
