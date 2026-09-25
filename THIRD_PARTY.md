# Third-party references

Runtime call-site signatures in `sora_bilingual/game/hooks.py` are adapted from Tom (tomrock645)'s
`PC_Steam_Sora_no_Kiseki_the_2nd.js` in https://github.com/0xDC00/scripts,
commit `8ae79b998e34aa75758725331d56d4e2226f1ae0`.

MIT License

Copyright (c) 2021 0xDC00

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

File-format references (no bundled game data):

- https://github.com/coinkillerl/FPACker — FPAC container layout.
- https://github.com/Aureole-Suite/Ingert — #scp binary layout.
- https://github.com/lmaple0/sora2looseload — independently verified loader;
  the native font experiment installs its MIT-licensed `xinput1_4.dll`
  (SHA-256 `e08a18068a482bb5d187a62023759c0e14ab69d76395b773ef0405d35e2ac8c7`).
  Source revision `745cf90`; see the upstream repository for its MIT license.
  The loader binary is not redistributed in this project.

Merged FNT and DDS files contain locally extracted game font data. They are
generated on the user's machine and excluded from Git and redistribution.

Runtime dependencies (bundled in the portable release under `runtime/<id>/`):

| Project | Use |
|---|---|
| [Frida](https://github.com/frida/frida) | Native process instrumentation |
| [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/) | Settings and resident status UI |
| [pygame-ce / SDL](https://github.com/pygame-community/pygame-ce) | Controller input |
| [pefile](https://github.com/erocarrera/pefile) | Executable inspection |
| [python-lz4 / LZ4](https://github.com/python-lz4/python-lz4) | Font-texture compression |

Python dependencies and their transitive dependencies retain their own licenses.
See each installed distribution's license files and upstream documentation.

The portable package includes the official CPython 3.14.7 embeddable distribution
([release and source](https://www.python.org/downloads/release/python-3147/)),
with its license in `runtime/<id>/LICENSE.txt`. Its upstream SHA-256 is pinned
in `tools/build_portable.py`.

Wheel license directories and distribution metadata are preserved under
`runtime/<id>/Lib/site-packages/*dist-info/` (including `licenses/` where supplied).
Qt/PySide and SDL are dynamically loaded and remain replaceable under their
licenses; no modifications to those libraries are made. PySide6 Essentials
contains the Qt modules used by this application; unused Qt Addons are not included.
Sources: [Qt 6.11](https://download.qt.io/archive/qt/6.11/),
[PySide sources](https://code.qt.io/cgit/pyside/pyside-setup.git/),
[pygame-ce sources](https://github.com/pygame-community/pygame-ce/releases).
The Windows launcher uses the .NET Framework included in supported Windows versions.

Copies of the GNU LGPLv3 and GPLv3 texts from Qt for Python v6.11.2 are also
included in `licenses/`. Library sources and notices are available from the
upstream projects linked above. Users may modify or replace the dynamically
loaded libraries and debug those changes; this project adds no restriction
on those rights. Modifying installed files disables automatic overwrites so
that such local changes are preserved.
