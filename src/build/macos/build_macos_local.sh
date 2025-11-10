pip install Pillow
pip install Jinja2

python src/build/macos/macos_build_templates.py
rm -rf build/

# Only use entitlements for app store version, non app store version is not sandboxed
pyinstaller gemino.custom.spec --workpath build/build --distpath build/dist/app -y
rm -rf build/dist/app/gemino
rm -rf build/build