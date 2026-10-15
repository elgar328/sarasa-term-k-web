# Releasing

How to publish `@elgar328/sarasa-term-k` for a new Sarasa Gothic release. npm versions can never be reused, so everything is verified on the exact tarball before it is published.

The package version is the same as the Sarasa Gothic release it is built from. It is set only in `scripts/build.py`.

## 1. Update the version

In `scripts/build.py`, set:

- `SARASA_VERSION` to the new release
- `ARCHIVE_SHA256` to the sha256 of `SarasaTermK-TTF-<version>.7z` (without the `sha256:` prefix this prints):

```sh
gh release view v<version> -R be5invis/Sarasa-Gothic --json assets \
  -q '.assets[] | select(.name == "SarasaTermK-TTF-<version>.7z") | .digest'
```

Then update the jsDelivr URLs in `README.md`. `check.py` fails if any version in the READMEs differs from `SARASA_VERSION`.

## 2. Build and check

Set up the environment as described in [README.md](README.md#building), then:

```sh
py scripts/build.py fetch --cache "$cache"
py scripts/build.py build --ttf-dir "$cache/ttf"
py scripts/check.py --ttf-dir "$cache/ttf"
```

The npm package must stay under jsDelivr's 150 MB limit. `check.py` prints the packed and unpacked size. The total size and per-style details are in `build/report.json`.

## 3. Test the tarball

```sh
work=$(mktemp -d)
npm pack ./dist --pack-destination "$work"
tar xzf "$work"/elgar328-sarasa-term-k-<version>.tgz -C "$work"
py scripts/browser_test.py --pkg "$work/package" --shots "$work/shots"
```

Look through the screenshots in `$work/shots`.

## 4. Publish a release candidate

Copy `dist/`, set the version to `<version>-rc.0`, and pack it:

```sh
cp -R dist "$work/rc"
(cd "$work/rc" && npm version <version>-rc.0 --no-git-tag-version)
npm pack "$work/rc" --pack-destination "$work"
```

Compare it with the tested tarball; only `package.json` should differ. Then publish it under the `next` tag, so `latest` does not change:

```sh
npm publish "$work"/elgar328-sarasa-term-k-<version>-rc.0.tgz --tag next
```

Check it through jsDelivr:

```sh
curl -sI https://cdn.jsdelivr.net/npm/@elgar328/sarasa-term-k@<version>-rc.0/400.css
py scripts/browser_test.py --base-url https://cdn.jsdelivr.net/npm/@elgar328/sarasa-term-k@<version>-rc.0 --shots "$work/shots-cdn"
```

A new version can take a few minutes to appear on jsDelivr.

## 5. Publish

Publish the tarball tested in step 3, unchanged:

```sh
npm publish "$work"/elgar328-sarasa-term-k-<version>.tgz
```

If npm asks for a one-time password, add `--otp=<code>`.

Then tag the commit and push:

```sh
git tag v<version>
git push origin main v<version>
```
