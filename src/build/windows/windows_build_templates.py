from jinja2 import Template
import os

VERSION = "2.9.0"
VERSION_MSIX = "2.9.0.0"
AUTHOR = "Francesco Servida"
NAME = "gemino"
DESCRIPTION = "Gemino File Duplicator"
CWD = os.getcwd()

with open('src/build/windows/version_info.py.j2') as src:
    with open('src/build/windows/version_info.py', "w") as dst:
        dst.write(Template(src.read()).render(version=VERSION, author=AUTHOR, app_name=NAME))

with open('src/build/windows/Installer.nsi.j2') as src:
    with open('src/build/windows/Installer.nsi', "w") as dst:
        dst.write(Template(src.read()).render(version=VERSION, author=AUTHOR, app_name=NAME))

with open('src/build/windows/msix_template.xml.j2') as src:
    with open('src/build/windows/msix_template.xml', "w") as dst:
        dst.write(Template(src.read()).render(version=VERSION, version_msix=VERSION_MSIX, author=AUTHOR, app_name=NAME, description=DESCRIPTION, cwd=CWD))