pip install Pillow
pip install Jinja2

python src/build/macos/macos_build_templates.py
rm -rf build/

# Only use entitlements for app store version, non app store version is not sandboxed
pyinstaller gemino.appstore.spec --workpath build/build --distpath build/dist/appstore -y
cp embedded.provisionprofile build/dist/appstore/gemino.app/Contents/
codesign --force --timestamp --verbose --options runtime --entitlements src/build/macos/entitlements.plist --sign '3rd Party Mac Developer Application: Francesco Servida (UVXFW83BXV)' build/dist/appstore/gemino.app

rm -rf build/dist/appstore/gemino

productbuild --sign "3rd Party Mac Developer Installer: Francesco Servida (UVXFW83BXV)" --component build/dist/appstore/gemino.app /Applications build/dist/gemino.pkg