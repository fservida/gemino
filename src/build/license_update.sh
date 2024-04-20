echo "# Licensing\nGemino relies on and packages the following software. All rights to the below software belong to the respective authors. Gemino uses the software according to the  licensing agreements below.\n\n" > LICENSES.md
pip-licenses --order=license --with-urls --with-authors --ignore-packages black --format=markdown >> LICENSES.md

# Licenses for JS libraries
echo '| pdf.js                    | 2.10.377   | Apache License 2.0                                                             | Mozilla                                                                                         | https://github.com/mozilla/pdf.js                        |' >> LICENSES.md
echo '| jszip                     | 3.10.1     | MIT License                                                                    | Stuart Knightley, David Duponchel, Franz Buchinger, António Afonso                              | https://stuk.github.io/jszip/                            |' >> LICENSES.md
echo '| docxjs                    | 0.3.0      | Apache License 2.0                                                             | Volodymyr Baydalka                                                                              | https://github.com/VolodymyrBaydalka/docxjs              |' >> LICENSES.md

echo '```'  >> LICENSES.md
pip-licenses --with-license-file --no-license-path --format=plain-vertical >> LICENSES.md
echo '```'  >> LICENSES.md