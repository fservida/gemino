import base64
import urllib.request


def download_file_to_base64(url):
    try:
        # Open the URL
        with urllib.request.urlopen(url) as response:
            # Read the data from the response
            data = response.read()
            # Write the data to the destination file
            return base64.b64encode(data).decode("utf-8")
    except Exception as e:
        print(f"Error downloading file: {e}")


# PDF (Apache License)
PDF_JS_MIN_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.10.377/pdf.min.js"
PDF_JS_MIN_WORKER_URL = (
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.10.377/pdf.worker.min.js"
)

JSZIP_JS_MIN_URL = "https://unpkg.com/jszip/dist/jszip.min.js"  # MIT License
DOCX_JS_MIN_URL = "https://raw.githubusercontent.com/VolodymyrBaydalka/docxjs/master/dist/docx-preview.min.js"  # Apache License

with open("viewer_libraries.py", "w") as pdf_libraries:
    pdf_libraries.write(f"PDF_JS_MIN = '{download_file_to_base64(PDF_JS_MIN_URL)}'\n")
    pdf_libraries.write(
        f"PDF_JS_MIN_WORKER = '{download_file_to_base64(PDF_JS_MIN_WORKER_URL)}'\n"
    )
    pdf_libraries.write(
        f"JSZIP_JS_MIN = '{download_file_to_base64(JSZIP_JS_MIN_URL)}'\n"
    )
    pdf_libraries.write(f"DOCX_JS_MIN = '{download_file_to_base64(DOCX_JS_MIN_URL)}'\n")
