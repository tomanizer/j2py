# VS Code Extension Development

Use this guide when changing the experimental VS Code extension in
`packages/j2py-vscode`.

For user-facing status and limitations, see [VS Code support](../VS_CODE.md) and the
[extension README](../../packages/j2py-vscode/README.md).

## Current Extension Surface

The extension currently provides:

- `j2py.translateFile`;
- `j2py.openSideBySide`;
- optional translate-on-save for Java files;
- TODO diagnostics for generated Python;
- status bar confidence summary;
- settings for executable path, output directory, translate-on-save, and LLM use.

It shells out to the configured `j2py` executable. It does not embed Python code or call
j2py internals directly.

## Ownership

| Area | File |
|------|------|
| Extension activation and commands | `packages/j2py-vscode/src/extension.ts` |
| VS Code command/settings manifest | `packages/j2py-vscode/package.json` |
| TypeScript build config | `packages/j2py-vscode/tsconfig.json` |
| Packaged-file exclusions | `packages/j2py-vscode/.vscodeignore` |
| User extension docs | `packages/j2py-vscode/README.md` |
| Main user docs | `docs/VS_CODE.md` |

## Adding Commands Or Settings

When adding a command:

1. Register it in `activate(...)` in `src/extension.ts`.
2. Add it to `contributes.commands` in `package.json`.
3. Keep command names under the `j2py.` namespace.
4. Document it in the extension README and `docs/VS_CODE.md`.

When adding a setting:

1. Add it under `contributes.configuration.properties`.
2. Read it through `vscode.workspace.getConfiguration("j2py")`.
3. Provide a conservative default.
4. Document the setting.

Do not make editor actions call live LLMs by default. `j2py.useLlm` is opt-in.

## Diagnostics And Integrations

The extension currently detects generated TODO markers. Future integration can add:

- `j2py doctor` JSON display;
- SARIF import or Problems panel mapping;
- SonarQube-adjacent diagnostics when a team already reviews through SonarLint/SonarQube;
- GitHub Copilot context files or commands that explain j2py output and diagnostics.

Keep integrations layered: the extension should surface j2py artifacts, not invent a
different assessment model.

## Local Validation

From `packages/j2py-vscode`:

```bash
npm ci
npm run compile
npm run package
```

For a smoke test:

1. Install the generated `.vsix` in a local VS Code window.
2. Configure `j2py.executable` to a working local command if needed.
3. Open a Java fixture.
4. Run `j2py: Translate Current File`.
5. Open the generated Python side by side.
6. Confirm TODO diagnostics and status bar state update.

If network is unavailable and `npm ci` cannot run, say so explicitly. Do not claim the
extension was validated by reading TypeScript only.

## Review Checklist

- `package.json` contributions match registered commands/settings.
- The extension still uses the CLI as the integration boundary.
- LLM use remains opt-in.
- README and `docs/VS_CODE.md` document new user-visible behavior.
- Compile and VSIX smoke status are reported honestly.
