# Dependency compatibility notes

## Yarn library publication workaround — 16 October 2026

Backstage's `@backstage/cli-module-package-manager-yarn` accepts `@yarnpkg/core ^4.9.1` and `@yarnpkg/cli ^4.7.0`. The published `@yarnpkg/core 4.9.2` instead refers to a `got` dependency through a patch file that exists only in Yarn's own source repository:

```text
patch:got@npm%3A11.8.2#~/.yarn/patches/got-npm-11.8.2-c1eb105458.patch
```

A fresh Backstage install consequently fails with `ENOENT` while trying to read that absent patch. The root `resolutions` temporarily pin the compatible library versions `@yarnpkg/core 4.9.1` and `@yarnpkg/cli 4.18.0`. Both satisfy the Backstage dependency ranges; CLI 4.18.1 requires the affected Core 4.9.2, hence both pins. The pinned Core uses the ordinary published `got ^11.7.0` dependency. This does not change the repository's Yarn executable, which remains 4.13.0.

Sources: published npm metadata for [Core 4.9.2](https://registry.npmjs.org/@yarnpkg/core/4.9.2), [Core 4.9.1](https://registry.npmjs.org/@yarnpkg/core/4.9.1), [CLI 4.18.0](https://registry.npmjs.org/@yarnpkg/cli/4.18.0), and [Backstage's Yarn module](https://registry.npmjs.org/@backstage/cli-module-package-manager-yarn/0.1.2). The missing [upstream patch at the published Core commit](https://github.com/yarnpkg/berry/blob/75ebe063092f86e47e4afeaf1ae4bdf24402874b/.yarn/patches/got-npm-11.8.2-c1eb105458.patch) prevents retries after a request promise settles. No empty or fabricated patch is included here.

Remove these two resolutions together after a corrected upstream publication has been verified with a fresh install, type checking and the Backstage build; update and commit `yarn.lock` at the same time.
