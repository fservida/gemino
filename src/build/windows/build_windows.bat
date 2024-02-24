pip install Pillow

del /f /s /q build 1>nul
rmdir /s /q build

python src\build\windows\windows_build_templates.py

pyinstaller src\main\python\main.py --version-file src\build\windows\version_info.py --onedir --workpath build\build --distpath build\dist --clean --windowed --noupx --icon src\main\icons\base\64.png -y -n gemino

cd build\dist\gemino
makensis /NOCD ..\..\..\src\build\windows\Installer.nsi

cd ..\..\..\