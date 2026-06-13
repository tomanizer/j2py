# j2py VS Code extension

This package shells out to the `j2py` CLI and adds editor affordances for reviewing
translations:

- `j2py: Translate Current File`
- `j2py: Open Side-by-Side`
- optional `j2py.translateOnSave`
- `TODO(j2py)` diagnostics in the Problems panel
- status bar confidence and rule/LLM summary after translation

Build a VSIX:

```bash
npm install
npm run compile
npm run package
```

Settings:

- `j2py.executable`: CLI path, defaults to `j2py`
- `j2py.outputDirectory`: translated Python output directory
- `j2py.translateOnSave`: translate Java files on save
- `j2py.useLlm`: allow LLM completion in editor-triggered translation
