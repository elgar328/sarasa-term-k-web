# Releasing

How to publish `@elgar328/sarasa-term-k` for a new Sarasa Gothic release. npm versions can never be reused, so the exact tarball that gets published is tested first, and a release candidate is checked on jsDelivr before the final version goes out.

The package version is the same as the Sarasa Gothic release it is built from. It is set only in `scripts/build.py`.

## 0. Before you start

- Install the tools listed in [README.md › Building](README.md#building). `gh` and `npm` must be logged in: check with `gh auth status` and `npm whoami`.
- Run everything from the repository root, in one bash or zsh session that you keep open until the end. Later steps use the variables defined in earlier ones.
- Start from an up-to-date, clean `main`: `git switch main && git pull`, then `git status` must show no changes.
- Run the first block of README › Building (`venv`, `py`, `playwright install`).
- See which versions are already on npm: `npm view @elgar328/sarasa-term-k versions` (E404 means nothing has been published yet).

## 1. Set the version

1. In `scripts/build.py`, set `SARASA_VERSION` to the new release. If you are publishing the version that is already set, leave it.
2. Read it back for the following steps:

   ```sh
   version=$(sed -n 's/^SARASA_VERSION = "\(.*\)"$/\1/p' scripts/build.py)
   echo "$version"
   ```

   This version must not appear in the npm list from step 0.
3. Get the sha256 of the release archive and set `ARCHIVE_SHA256` in `scripts/build.py` to it, without the `sha256:` prefix:

   ```sh
   gh release view "v$version" -R be5invis/Sarasa-Gothic --json assets \
     -q ".assets[] | select(.name == \"SarasaTermK-TTF-$version.7z\") | .digest"
   ```

   You don't need to compare it by hand: `build.py fetch` in step 2 stops if the download doesn't match `ARCHIVE_SHA256`.
4. Update the jsDelivr URLs in `README.md` to the new version. `check.py` fails if any version in the docs differs from `SARASA_VERSION`.
5. Commit, unless nothing changed:

   ```sh
   git commit -am "Update to Sarasa Gothic $version"
   ```

## 2. Build and check

```sh
cache=$(mktemp -d)
py scripts/build.py fetch --cache "$cache"
py scripts/build.py build --ttf-dir "$cache/ttf"
py scripts/check.py --ttf-dir "$cache/ttf"
```

`check.py` must end with `all checks passed`. Among other things, it fails if the npm package exceeds jsDelivr's 150 MB limit. Per-style details are in `build/report.json`.

## 3. Pack and test the release tarball

```sh
work=$(mktemp -d)
mkdir "$work/final"
npm pack ./dist --pack-destination "$work/final"
final="$work/final/elgar328-sarasa-term-k-$version.tgz"
tar xzf "$final" -C "$work/final"
py scripts/browser_test.py --pkg "$work/final/package" --shots "$work/shots"
open "$work/shots"   # macOS; elsewhere, open the folder in a file manager
```

`browser_test.py` must end with `all browser checks passed`. Then check the screenshots:

- `*-styles.png`: ten rows with visibly different weights and real italics, Hangul exactly two Latin cells wide, and `→ ├──` drawn correctly.
- `*-compare.png`: the top row is the web font, the bottom row the locally installed Sarasa Term K (Courier if it is not installed). With Sarasa installed, the two rows should look the same.

`$final` is the file that will be published in step 5. Do not rebuild after this point.

## 4. Publish a release candidate

Set the candidate version. Use `-rc.0`, or the next free number if an earlier attempt already used it (see the npm list from step 0):

```sh
rc_version="$version-rc.0"
```

Make a copy of the package with that version and pack it into its own directory:

```sh
cp -R dist "$work/rc"
(cd "$work/rc" && npm version "$rc_version" --no-git-tag-version)
mkdir "$work/rc-out"
npm pack "$work/rc" --pack-destination "$work/rc-out"
rc="$work/rc-out/elgar328-sarasa-term-k-$rc_version.tgz"
mkdir "$work/rc-check" && tar xzf "$rc" -C "$work/rc-check"
diff -r "$work/final/package" "$work/rc-check/package"
```

The `diff` must show only the `"version"` line of `package.json`. It exits with status 1 because the files differ; that is expected.

Publish the candidate under the `next` tag:

```sh
npm publish "$rc" --tag next
npm view @elgar328/sarasa-term-k dist-tags
```

If npm asks for a one-time password, add `--otp=<code>`. `latest` stays on the previous release. On the very first release there is no previous one, so `latest` may point at the candidate until step 5.

Check the candidate on jsDelivr. A new version can take a few minutes to appear; if you get a 404, wait and try again.

```sh
curl -sI "https://cdn.jsdelivr.net/npm/@elgar328/sarasa-term-k@$rc_version/400.css" | head -1
py scripts/browser_test.py --base-url "https://cdn.jsdelivr.net/npm/@elgar328/sarasa-term-k@$rc_version" --shots "$work/shots-cdn"
```

`curl` must print a `200` status line, and `browser_test.py` must pass.

## 5. Publish the release

Publish the tarball tested in step 3, unchanged. Use `$final`, not the candidate in `$work/rc-out`. Publishing it moves `latest` to `$version`.

```sh
npm publish "$final"
npm dist-tag rm @elgar328/sarasa-term-k next
npm view @elgar328/sarasa-term-k dist-tags
```

`dist-tags` must show `latest` set to `$version` and no `next`. Add `--otp=<code>` if npm asks for it.

Check the release on jsDelivr; it must print a `200` status line:

```sh
curl -sI "https://cdn.jsdelivr.net/npm/@elgar328/sarasa-term-k@$version/400.css" | head -1
```

Tag the commit you built from (`HEAD`), push, and clean up. The last line also removes the build output, so a later run can't pick up a stale `dist/`:

```sh
git tag "v$version"
git push origin main "v$version"
rm -rf "$venv" "$cache" "$work" dist build
```
