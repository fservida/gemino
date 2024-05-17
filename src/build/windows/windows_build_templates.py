from jinja2 import Template
import os

VERSION = "2.9.0"
AUTHOR = "Francesco Servida"
NAME = "gemino"

# MSIX
VERSION_MSIX = f"{VERSION}.0"
DESCRIPTION = "Gemino File Duplicator"
CWD = os.getcwd()
PACKAGE_NAME = "61426FrancescoServida.gemino"
PUBLISHER_NAME = "CN=78725267-FDD0-4FCD-AD26-2A4A4570ED25"

with open('src/build/windows/version_info.py.j2') as src:
    with open('src/build/windows/version_info.py', "w") as dst:
        dst.write(Template(src.read()).render(version=VERSION, author=AUTHOR, app_name=NAME))

with open('src/build/windows/Installer.nsi.j2') as src:
    with open('src/build/windows/Installer.nsi', "w") as dst:
        dst.write(Template(src.read()).render(version=VERSION, author=AUTHOR, app_name=NAME))

with open('src/build/windows/msix_template.xml.j2') as src:
    with open('src/build/windows/msix_template.xml', "w") as dst:
        dst.write(Template(src.read()).render(version=VERSION, version_msix=VERSION_MSIX, author=AUTHOR, app_name=NAME, description=DESCRIPTION, cwd=CWD, package_name=PACKAGE_NAME, publisher_name=PUBLISHER_NAME))