# j2py VS Code extension

This extension is experimental. The stable VS Code-adjacent workflow is still the
`j2py compare` CLI command, which opens a Java/Python side-by-side diff through `code`
or another compatible editor.

This package shells out to the `j2py` CLI and adds editor affordances for reviewing
translations:

- `j2py: Translate Current File`
- `j2py: Open Side-by-Side`
- optional `j2py.translateOnSave`
- `TODO(j2py)` diagnostics in the Problems panel
- status bar confidence and rule/LLM summary after translation

## Build

Build a VSIX from this directory:

```bash
npm install
npm run compile
npm run package
```

Install the generated `.vsix` with the VS Code command `Extensions: Install from VSIX...`.

## Settings

- `j2py.executable`: CLI path, defaults to `j2py`
- `j2py.outputDirectory`: translated Python output directory
- `j2py.translateOnSave`: translate Java files on save
- `j2py.useLlm`: allow LLM completion in editor-triggered translation

Example workspace settings:

```json
{
  "j2py.executable": "j2py",
  "j2py.outputDirectory": "${workspaceFolder}/translated_py",
  "j2py.translateOnSave": false,
  "j2py.useLlm": false
}
```

## Current Limits

- No automated VS Code extension tests are checked in yet.
- CI does not yet prove `npm ci`, TypeScript compilation, or VSIX packaging.
- The extension surfaces generated-output TODOs, but it does not yet surface full
  `j2py doctor` findings.
- SARIF and SonarQube workflows are CLI/CI workflows today, not direct extension
  features.
- `j2py-wire`, config suggestions, dashboards, and assessment reports are not exposed as
  extension commands yet.

See `docs/VS_CODE.md` for the user-facing status, workflow, and validation checklist.
