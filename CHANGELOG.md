# Changelog

## 4.0.1

- Add a portable Windows x64 EXE with Python, tkinter, and the weapon database bundled.
- Restore readable source files directly in the repository and source ZIP.
- Remove the obsolete split archives and damaged legacy ZIP rebuild path.
- Use VERSION for the window title, executable metadata, and release filenames.
- Add Windows source/EXE startup checks, archive checks, and save regression checks.
- Include source commit/file hashes in BUILD_INFO.json and ZIP checksums in SHA256SUMS.txt.
- Publish from the exact tested commit only after the Windows build passes.
- Preserve the existing v4.0.0 release and its tag.
- Supply the missing docs directory used by the repository's existing GitHub Pages setup.

Save offsets, editing features, and BLES00825 region restrictions are unchanged.
The release checks use synthetic saves; no new in-game compatibility is claimed.

## 4.0.0

Initial source-only public release. The final published ZIP passed its recorded
SHA-256 and ZIP integrity checks after the source-chunk corrections.
