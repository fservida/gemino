from jinja2 import Template

VERSION = "2.9.0"
AUTHOR = "Francesco Servida"
NAME = "gemino"

with open('src/build/windows/version_info.py.j2') as src:
    with open('src/build/windows/version_info.py', "w") as dst:
        dst.write(Template(src.read()).render(version=VERSION, author=AUTHOR, app_name=NAME))

with open('src/build/windows/Installer.nsi.j2') as src:
    with open('src/build/windows/Installer.nsi', "w") as dst:
        dst.write(Template(src.read()).render(version=VERSION, author=AUTHOR, app_name=NAME))