# Gosom FoodScan temporary Windows build

This executable preserves Gosom **v1.18.1** and replaces only its `github.com/gosom/scrapemate` dependency with a locally patched copy of **v1.4.0**. The official binary remains unchanged at `tools/gosom/gosom.exe`.

## Applied patches

1. `adapters/fetchers/jshttp/jshttp.go:295,348`: Chromium arguments now come from `chromiumArgs()` and omit `--single-process`. That flag causes Playwright browser crashes on Windows; see [gosom/scrapemate#18](https://github.com/gosom/scrapemate/issues/18).
2. `adapters/fetchers/jshttp/session_slot.go:218`: `playwrightPage.isClosed()` now returns the actual `Page.IsClosed()` state instead of its inverse.
3. `adapters/fetchers/jshttp/session_slot.go:80-89`: after successful browser recreation, `acquirePage()` continues to `primaryPage()` and cannot return `(nil, nil)`.
4. `foodscan_patch_internal_test.go`: regression tests cover open/closed state, successful browser recovery returning a non-nil page, and absence of `--single-process`.

The Gosom source `go.mod` uses:

```text
replace github.com/gosom/scrapemate => ../scrapemate-1.4.0
```

## Reproduction and verification

The public distribution contains `patch/scrapemate-foodscan.patch`. Download the pinned
upstream archives named in `VERSION.json`, place them beside `build.ps1`, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The script applies the patch, runs the focused regression package, builds Gosom with
`-trimpath`, and prints the resulting SHA-256. Normal users receive the same pinned
binary through the GitHub Release Asset described by `VERSION.json`; Go is not part of
the normal setup path.

- Official binary, one page/browser: `unexpected page type`.
- Official binary, two pages/browser: `playwright: target closed`.
- Patched browser smoke: 16 places, all with title and category.
- Patched ten-query test: 10/10 inputs complete, 162 CSV records, all with title and category.
- Patched small-grid test: four points in four separate batches, 64 CSV records and zero failed inputs.
- Re-running the completed grid manifest resumed in 0.123 seconds without repeating finished inputs.
- Scrapemate jshttp tests: pass, including the three FoodScan regression tests.

The full upstream Scrapemate suite is not Windows-clean: its root test package calls Unix-only `syscall.Kill` in `scrapemate_test.go:330` and does not compile on Windows. All other packages reached by `go test ./...`, including `adapters/browsers/playwright`, `adapters/fetchers/jshttp`, proxy, providers and the app package, pass. This upstream test portability defect is unrelated to the FoodScan patch.

## Integrity

```text
gosom-foodscan.exe
SHA-256 c879e7d60903101ef1c0a97799f58d47cbfa37d9d0b8cfcd884695a44b77404a

gosom v1.18.1 source archive
SHA-256 e44b4b66bf578c8d7dd17fac97d84ee3d59a46c0ef478b089aa59eaf126821a6

scrapemate v1.4.0 source archive
SHA-256 e0057db4ee576858d526279c63220f796a3dbccde41893006c997981c7fa4fdc
```

Run the browser regression suite after any official Gosom update. Return to the official binary when upstream contains equivalent fixes and all browser tests pass.
