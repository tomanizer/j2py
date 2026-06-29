# Case study - translating Apache Commons Codec Hex end-to-end

Status: **Active** (issue [#656](https://github.com/tomanizer/j2py/issues/656), child
of external-library epic [#655](https://github.com/tomanizer/j2py/issues/655)).

This case study is the second external-library closed loop after
[`java-semver`](CASE_STUDY_JSEMVER.md). It translates a focused Apache Commons Codec
`Hex` slice with the deterministic rule layer only, links the translated classes in a
test harness, and runs upstream-derived pytest assertions against the translated Python.

## The subject

[Apache Commons Codec](https://github.com/apache/commons-codec), tag
`rel/commons-codec-1.22.0`, commit `81a6295f071df5819893422a397d94bc396f2edd`, Apache
License 2.0.

The hermetic fixture under
[`tests/fixtures/case_study/commons_codec_hex/java/`](../tests/fixtures/case_study/commons_codec_hex/java)
contains only the scoped production source plus the upstream assertion source:

- `org.apache.commons.codec.binary.Hex`
- `BinaryEncoder`, `BinaryDecoder`
- `EncoderException`, `DecoderException`
- `HexTest.java` for the focused pytest port

This slice was chosen because it stresses byte/char arrays, static helpers, overload
dispatch, checked exceptions, and Java signed-byte behavior without requiring a full
platform migration.

## Rule-layer translation metrics

Rule layer only, no LLM (`translate_file(..., use_llm=False, validate=False)`):

| File | Node coverage | `# TODO(j2py)` | Confidence | Semantic warnings |
|---|---:|---:|---:|---:|
| `BinaryDecoder.java` | 100% | 0 | 1.00 | 0 |
| `BinaryEncoder.java` | 100% | 0 | 1.00 | 0 |
| `DecoderException.java` | 100% | 0 | 0.99 | 6 |
| `EncoderException.java` | 100% | 0 | 0.99 | 5 |
| `Hex.java` | 100% | 0 | 0.99 | 60 |

The translation is mechanically complete for the scoped files, but the first runnable
loop still needs explicit residual execution patches. That is the useful evidence here:
100% node coverage does not by itself prove executable library behavior.

## Closed loop

The pytest oracle is
[`tests/case_study/test_commons_codec_hex_case_study.py`](../tests/case_study/test_commons_codec_hex_case_study.py),
backed by
[`tests/case_study/commons_codec_hex_harness.py`](../tests/case_study/commons_codec_hex_harness.py).

Result: **24 / 24 focused upstream-derived Hex assertions pass** against the linked
rule-layer translation.

Covered surface:

- empty byte/char/string inputs;
- lower-case and upper-case `encodeHex` / `encodeHexString`;
- partial byte-array encoding;
- decode into an existing output buffer;
- odd-length and illegal-character `DecoderException` paths;
- Java signed-byte behavior for values such as `0x80` and `0xff`.

Deliberately excluded from the first slice:

- `ByteBuffer` read/position/limit behavior;
- full charset matrix and unsupported-charset behavior;
- randomized upstream loops;
- instance `encode(Object)` / `decode(Object)` paths that rely on broader `String`,
  `ByteBuffer`, and cast behavior.

## External-dependency stubs

These are JDK or platform symbols outside the tested Commons Codec logic. They are
scaffolding, not residual translator patches:

- `ByteBuffer` marker for dispatcher guards; ByteBuffer behavior is out of scope here.
- `Charset`, `StandardCharsets`, and `CharEncoding` enough to initialize `Hex`.
- `Character.digit` for hexadecimal digit conversion.

## Residual translator defects

The harness locks these defects in `_RESIDUAL_GAP_PATCHES`; future rule-layer fixes should
remove the corresponding patch and update this table.

| Gap id | Module | Generated-output defect |
|---|---|---|
| `CODEC-HEX-1` | `Hex` | `char[]` one-argument overload dispatcher is emitted as an impossible/null `str` guard. |
| `CODEC-HEX-2` | `Hex` | `decodeHex(char[], byte[], int)` guard expects `str` instead of list-backed `char[]`. |
| `CODEC-HEX-3` | `Hex` | One-character `String` inputs are shadowed by a mistaken `char[]` branch. |
| `CODEC-HEX-5` | `Hex` | Java `%,d` format tokens are not normalized for Python `%` formatting. |
| `CODEC-HEX-6` | `Hex` | `new char[dataLen << 1]` loses allocation parentheses. |
| `CODEC-HEX-7` | `Hex` | `new char[dataLength << 1]` loses allocation parentheses. |
| `CODEC-HEX-8` | `Hex` | Six-argument `encodeHex(..., char[] alphabet, char[] out, ...)` guards use `str`. |
| `CODEC-HEX-9` | `Hex` | Six-argument `encodeHex(..., boolean, char[] out, ...)` output guard uses `str`. |
| `CODEC-HEX-10` | `Hex` | Two-argument `encodeHex(byte[], char[] alphabet)` guard uses `str`. |
| `CODEC-HEX-11` | `Hex` | ByteBuffer/alphabet overload guard uses `str` for the alphabet. |
| `CODEC-HEX-14` | `Hex` | A Java `void` overload dispatcher branch delegates, then falls through to `TypeError`. |

## Follow-ups

1. Promote the dispatcher and allocation issues into general rule-layer fixes with small
   Java/Python fixture pairs.
2. Add a bounded `ByteBuffer` stub or rule-layer support only when a test genuinely needs
   position/limit behavior.
3. Expand the oracle to instance `encode` / `decode` after `String.getBytes`,
   `new String(byte[], Charset)`, and cast/classification behavior are handled.
4. Defer `Base64` until the Hex residual list is smaller and ByteBuffer handling has a
   clear owner. Base64 is still the natural next Commons Codec expansion, but starting it
   now would mix a new algorithm with unresolved harness/runtime gaps.
