# Security policy

## Reporting a vulnerability

Report security issues privately to **thomas.haederle@gmail.com**.

Please include: description, reproduction steps, potential impact, and any suggested fix.

We aim to respond within 7 days and disclose publicly within 30 days of a fix landing.

## Scope

In scope:
- Supply-chain issues (compromised dependencies, build artifacts)
- Prompt injection via crafted Java source fed to the LLM layer
- Path traversal in file I/O (input source paths, output paths)

Out of scope:
- The translated Python code itself — j2py makes no guarantees about the security
  properties of the output; that is the responsibility of the Java source author
- Performance issues (timeouts, memory) that are not exploitable
