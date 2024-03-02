pip install Pillow
pip install Jinja2

echo $MACOS_PROVISIONING_PROFILE | base64 --decode > embedded.provisionprofile
ls -lah

python src/build/macos/macos_build_templates.py

rm -rf build/
pyinstaller gemino.custom.spec --workpath build/build --distpath build/dist/app -y
rm -rf build/dist/app/gemino
rm -rf build/build

# Only use entitlements for app store version, non app store version is not sandboxed
pyinstaller gemino.appstore.spec --workpath build/build --distpath build/dist/appstore -y
cp embedded.provisionprofile build/dist/appstore/gemino.app/Contents/
codesign --force --timestamp --verbose --options runtime --entitlements src/build/macos/entitlements.plist --sign '3rd Party Mac Developer Application: Francesco Servida (UVXFW83BXV)' build/dist/appstore/gemino.app
rm -rf build/dist/appstore/gemino

# Store the notarization credentials so that we can prevent a UI password dialog
# from blocking the CI

echo "Create keychain profile"
echo $MACOS_NOTARIZATION_KEY | base64 --decode > authkey.p8
xcrun notarytool store-credentials -k authkey.p8 -d $MACOS_NOTARIZATION_KEY_ID -i $MACOS_NOTARIZATION_ISSUER notarytool-profile
rm -P authkey.p8

# We can't notarize an app bundle directly, but we need to compress it as an archive.
# Therefore, we create a zip file containing our app bundle, so that we can send it to the
# notarization service

echo "Creating temp notarization archive"
ditto -c -k --keepParent "build/dist/app/gemino.app" "notarization.zip"

# Here we send the notarization request to the Apple's Notarization service, waiting for the result.
# This typically takes a few seconds inside a CI environment, but it might take more depending on the App
# characteristics. Visit the Notarization docs for more information and strategies on how to optimize it if
# you're curious

echo "Notarize app"
xcrun notarytool submit "notarization.zip" --keychain-profile "notarytool-profile" --wait

# Finally, we need to "attach the staple" to our executable, which will allow our app to be
# validated by macOS even when an internet connection is not available.
echo "Attach staple"
xcrun stapler staple -v "build/dist/app/gemino.app"

git clone https://github.com/create-dmg/create-dmg.git
create-dmg/create-dmg --volname gemino --app-drop-link 10 10 build/dist/gemino.dmg build/dist/app

codesign -fvs "Developer ID Application: Francesco Servida (UVXFW83BXV)" build/dist/gemino.dmg
xcrun notarytool submit build/dist/gemino.dmg --keychain-profile "notarytool-profile" --wait
# Finally, we need to "attach the staple" to our dmg, which will allow the image to be
# validated by macOS even when an internet connection is not available.
echo "Attach staple"
xcrun stapler staple -v "build/dist/gemino.dmg"


productbuild --sign "3rd Party Mac Developer Installer: Francesco Servida (UVXFW83BXV)" --component build/dist/appstore/gemino.app /Applications build/dist/gemino.pkg