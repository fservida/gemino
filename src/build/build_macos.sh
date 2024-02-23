pip install Pillow
rm -rf build/
pyinstaller src/main/python/main.py --workpath build/build --distpath build/dist/app --clean --osx-bundle-identifier ch.francescoservida.gemino --codesign-identity "Developer ID Application: Francesco Servida (UVXFW83BXV)" --windowed --icon src/main/icons/mac/256.png -y -n gemino
rm -rf build/dist/app/gemino
git clone https://github.com/create-dmg/create-dmg.git
create-dmg/create-dmg --volname gemino --app-drop-link 10 10 build/dist/gemino.dmg build/dist/app
