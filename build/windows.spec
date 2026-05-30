# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

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
    ],
    hiddenimports=['win10toast', 'PyQt5.QtSvg'],
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
    name='Chess Claim Tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='..\\icons\\logo.ico',
)
