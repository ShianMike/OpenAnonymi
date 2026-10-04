# Reviewed PDF fonts

These original, unmodified Noto fonts are bundled for offline reviewed PDF output.
`manifest.json` records each pinned upstream commit, source URL, byte count and
SHA-256. The renderer verifies hashes before using them and caches only public
font metadata. It embeds only the subsets needed by the current reviewed text.

The SIL Open Font License 1.1 notices are preserved in `OFL-Noto.txt` for the
Latin/Greek/Cyrillic, Arabic, Devanagari and Hebrew fonts, `OFL-CJK.txt` for the
Japanese CJK variable font, and `OFL-Emoji.txt` for the monochrome emoji font.
The upstream repositories are [Noto fonts](https://github.com/notofonts/noto-fonts),
[Noto CJK](https://github.com/notofonts/noto-cjk) and
[Google Fonts Noto Emoji](https://github.com/google/fonts/tree/main/ofl/notoemoji).

This bundle does not cover every Unicode character. Unsupported glyphs fail
closed with a fixed message offering TXT or Word; they are never silently dropped.
No source text, font subset or generated document is cached across requests.
The Docker image copies these assets with `app`; PDFium is a development-only
independent test reader and renderer.
