# Vendored fixture: Apache Commons Codec `Hex`

The `java/` sources are copied verbatim (Apache License 2.0) from Apache Commons Codec
(https://github.com/apache/commons-codec), tag `rel/commons-codec-1.22.0`, commit
`81a6295f071df5819893422a397d94bc396f2edd`.

Vendored production sources:

- `org.apache.commons.codec.binary.Hex`
- `org.apache.commons.codec.BinaryDecoder`
- `org.apache.commons.codec.BinaryEncoder`
- `org.apache.commons.codec.DecoderException`
- `org.apache.commons.codec.EncoderException`

`HexTest.java` is also vendored as the upstream assertion source for the focused pytest
port in `tests/case_study/test_commons_codec_hex_case_study.py`. Each file retains its
original ASF license header.

They are vendored so the end-to-end case study
(docs/CASE_STUDY_COMMONS_CODEC_HEX.md, issue #656) runs hermetically in `make check`
without a corpus checkout. They are inputs to the j2py translator, not j2py source code.
