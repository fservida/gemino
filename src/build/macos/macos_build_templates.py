from jinja2 import Template
from datetime import datetime

VERSION = "2.8.0"
CURRENT_DATE = datetime.now().strftime("%Y%m%d%H%M")

# Build for custom distribution
with open('src/build/macos/gemino.spec.j2') as src:
    with open('gemino.custom.spec', "w") as dst:
        dst.write(Template(src.read()).render(version=VERSION, developer_id="Developer ID Application: Francesco Servida (UVXFW83BXV)", entitlements_file="", current_date=CURRENT_DATE))

# Build for appstore distribution (sandboxed)
with open('src/build/macos/gemino.spec.j2') as src:
    with open('gemino.appstore.spec', "w") as dst:
        dst.write(Template(src.read()).render(version=VERSION, developer_id="3rd Party Mac Developer Application: Francesco Servida (UVXFW83BXV)", entitlements_file="", current_date=CURRENT_DATE))