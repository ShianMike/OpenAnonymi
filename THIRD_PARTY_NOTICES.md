# Third-party notices

OpenAnonymi's license does not replace the licenses of its dependencies or
bundled third-party material. Preserve those notices when redistributing.

| Material | License and notice |
| --- | --- |
| Figtree interface font | SIL OFL 1.1, `frontend/src/assets/fonts/Figtree-OFL.txt` |
| Noto PDF fonts | SIL OFL 1.1, notices and pinned manifests in `backend/app/assets/fonts` |
| English OCR model | Apache-2.0, `backend/app/assets/ocr/LICENSE` and manifest |
| Disposable email domain list | Its upstream notice, `backend/app/accounts/data/disposable_domains.LICENSE` |
| Authored detection corpus | CC0-1.0, stated in its fixture files |
| libtiff in the Linux image | Upstream license copied to `/usr/share/doc/openanonymi-libtiff/LICENSE.md` |

Python dependencies and the English spaCy model are pinned in `backend/uv.lock`.
JavaScript dependencies are pinned in `frontend/package-lock.json`. Their
installed distributions contain their own license notices. Native wheels can
bundle additional libraries; review those notices when redistributing an image.

The production Docker image retains installed dependency notices and bundled
asset licenses. Its project license and notice are copied to
`/usr/share/doc/openanonymi`.
