import * as childProcess from "child_process";
import * as path from "path";
import * as vscode from "vscode";

type J2pyResult = {
  file: string;
  output: string | null;
  confidence: number;
  used_llm: boolean;
  todos: string[];
  validation: { ok: boolean } | null;
};

let diagnostics: vscode.DiagnosticCollection;
let statusBar: vscode.StatusBarItem;
let highConfidenceDecoration: vscode.TextEditorDecorationType;
let mediumConfidenceDecoration: vscode.TextEditorDecorationType;
let lowConfidenceDecoration: vscode.TextEditorDecorationType;

export function activate(context: vscode.ExtensionContext): void {
  diagnostics = vscode.languages.createDiagnosticCollection("j2py");
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 80);
  statusBar.command = "j2py.translateFile";
  highConfidenceDecoration = vscode.window.createTextEditorDecorationType({
    overviewRulerLane: vscode.OverviewRulerLane.Left,
    overviewRulerColor: "#34a853",
  });
  mediumConfidenceDecoration = vscode.window.createTextEditorDecorationType({
    overviewRulerLane: vscode.OverviewRulerLane.Left,
    overviewRulerColor: "#fbbc04",
  });
  lowConfidenceDecoration = vscode.window.createTextEditorDecorationType({
    overviewRulerLane: vscode.OverviewRulerLane.Left,
    overviewRulerColor: "#ea4335",
  });
  context.subscriptions.push(
    diagnostics,
    statusBar,
    highConfidenceDecoration,
    mediumConfidenceDecoration,
    lowConfidenceDecoration,
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("j2py.translateFile", translateActiveFile),
    vscode.commands.registerCommand("j2py.openSideBySide", openSideBySide),
    vscode.workspace.onDidSaveTextDocument(async (document) => {
      const config = vscode.workspace.getConfiguration("j2py");
      if (document.languageId === "java" && config.get<boolean>("translateOnSave")) {
        await translateDocument(document);
      }
      if (document.languageId === "python") {
        refreshTodoDiagnostics(document);
      }
    }),
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (editor) {
        updateStatus(editor.document);
        if (editor.document.languageId === "python") {
          refreshTodoDiagnostics(editor.document);
        }
      }
    }),
  );

  if (vscode.window.activeTextEditor) {
    updateStatus(vscode.window.activeTextEditor.document);
  }
}

export function deactivate(): void {
  diagnostics?.dispose();
  statusBar?.dispose();
}

async function translateActiveFile(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "java") {
    vscode.window.showWarningMessage("Open a Java file before running j2py translation.");
    return;
  }
  await translateDocument(editor.document);
}

async function translateDocument(document: vscode.TextDocument): Promise<void> {
  await document.save();
  const outputPath = translatedPath(document.uri.fsPath);
  const result = await runJ2py(document.uri.fsPath, outputPath);
  statusBar.text = `j2py: ${Math.round(result.confidence * 100)}% | ${
    result.used_llm ? "LLM" : "rule-only"
  }`;
  statusBar.show();

  const outputUri = vscode.Uri.file(outputPath);
  const outputDocument = await vscode.workspace.openTextDocument(outputUri);
  refreshTodoDiagnostics(outputDocument, result.todos);
  decorateConfidence(outputDocument, result);
}

async function openSideBySide(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return;
  }
  const javaPath = editor.document.languageId === "java"
    ? editor.document.uri.fsPath
    : javaPathForPython(editor.document.uri.fsPath);
  const pythonPath = translatedPath(javaPath);
  const left = await vscode.workspace.openTextDocument(vscode.Uri.file(javaPath));
  await vscode.window.showTextDocument(left, vscode.ViewColumn.One);
  const right = await vscode.workspace.openTextDocument(vscode.Uri.file(pythonPath));
  await vscode.window.showTextDocument(right, vscode.ViewColumn.Two);
}

function refreshTodoDiagnostics(document: vscode.TextDocument, todos?: string[]): void {
  const issues: vscode.Diagnostic[] = [];
  for (let index = 0; index < document.lineCount; index += 1) {
    const line = document.lineAt(index);
    if (line.text.includes("TODO(j2py)") || line.text.includes("__j2py_todo__")) {
      issues.push(
        new vscode.Diagnostic(
          line.range,
          todos?.find((todo) => line.text.includes(todo.replace("#", "").trim())) ??
            line.text.trim(),
          vscode.DiagnosticSeverity.Warning,
        ),
      );
    }
  }
  diagnostics.set(document.uri, issues);
}

function decorateConfidence(document: vscode.TextDocument, result: J2pyResult): void {
  const severity = result.todos.length > 0 || result.confidence < 0.8
    ? "low"
    : result.used_llm
      ? "medium"
      : "high";
  const decoration = severity === "high"
    ? highConfidenceDecoration
    : severity === "medium"
      ? mediumConfidenceDecoration
      : lowConfidenceDecoration;
  const editor = vscode.window.visibleTextEditors.find(
    (item) => item.document.uri.fsPath === document.uri.fsPath,
  );
  if (editor) {
    const range = new vscode.Range(0, 0, Math.max(document.lineCount - 1, 0), 0);
    editor.setDecorations(decoration, [range]);
  }
}

function updateStatus(document: vscode.TextDocument): void {
  if (document.languageId === "java") {
    statusBar.text = "j2py: translate";
    statusBar.show();
  } else if (document.languageId === "python") {
    const todoCount = Array.from({ length: document.lineCount }, (_, index) => document.lineAt(index).text)
      .filter((line) => line.includes("TODO(j2py)") || line.includes("__j2py_todo__")).length;
    statusBar.text = todoCount ? `j2py: ${todoCount} TODOs` : "j2py";
    statusBar.show();
  } else {
    statusBar.hide();
  }
}

async function runJ2py(javaPath: string, outputPath: string): Promise<J2pyResult> {
  const config = vscode.workspace.getConfiguration("j2py");
  const executable = config.get<string>("executable") ?? "j2py";
  const useLlm = config.get<boolean>("useLlm") ?? false;
  await vscode.workspace.fs.createDirectory(vscode.Uri.file(path.dirname(outputPath)));
  const args = [
    "translate",
    javaPath,
    "--output",
    outputPath,
    "--json",
    useLlm ? "--llm" : "--no-llm",
  ];
  const { stdout, stderr } = await execFile(executable, args);
  if (stderr.trim()) {
    console.warn(stderr);
  }
  return JSON.parse(stdout) as J2pyResult;
}

function execFile(command: string, args: string[]): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    childProcess.execFile(command, args, (error, stdout, stderr) => {
      if (error) {
        reject(error);
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

function translatedPath(javaPath: string): string {
  const config = vscode.workspace.getConfiguration("j2py");
  const configured = config.get<string>("outputDirectory") ?? "${workspaceFolder}/j2py-output";
  const workspace = vscode.workspace.getWorkspaceFolder(vscode.Uri.file(javaPath));
  const outputRoot = configured.replace("${workspaceFolder}", workspace?.uri.fsPath ?? path.dirname(javaPath));
  return path.join(outputRoot, path.basename(javaPath, ".java") + ".py");
}

function javaPathForPython(pythonPath: string): string {
  const basename = path.basename(pythonPath, ".py") + ".java";
  const workspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  return workspace ? path.join(workspace, basename) : path.join(path.dirname(pythonPath), basename);
}
