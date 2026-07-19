RMDIR /s /q "./src/gemini_documentation/build"
RMDIR /s /q "./src/gemini_documentation/source/codedocumentation"
poetry run sphinx-build -M html ./src/gemini_documentation/source ./src/gemini_documentation/build --fail-on-warning