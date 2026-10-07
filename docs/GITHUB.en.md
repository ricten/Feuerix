# Putting the project on GitHub

*This is the English translation of [GITHUB.md](GITHUB.md); the German version is authoritative for this
project.*

## Preliminary note
The project is set up so it fits directly into a Git repository:
* `.gitignore` excludes `.env`, `openslides/secrets/` and build artefacts – **credentials never end up in the
  repository**.
* `.github/workflows/ci.yml` automatically runs the tests on every push (Django check, migrations, test
  suite against PostgreSQL).
* `scripts/github_einrichten.sh` handles `git init`, the first commit and the push in one step.

## One-time setup on GitHub (in the browser)
1. Create an account or sign in, **New repository**.
2. Name e.g. `feuerix`, visibility **Private** (contains club-specific details and shouldn't be public).
3. **Don't** let it add a README/.gitignore/license upfront (the repository needs to be empty).
4. Copy the address, e.g. `git@github.com:YOUR-NAME/feuerix.git` (SSH) or
   `https://github.com/YOUR-NAME/feuerix.git`.

## On your computer
Requires: `git` installed and signed in to GitHub – easiest with the GitHub CLI (`gh auth login`) or an SSH
key (GitHub › Settings › SSH keys).

```bash
git config --global user.name  "Your Name"
git config --global user.email "you@mail.com"

unzip feuerix.zip && cd feuerix
./scripts/github_einrichten.sh git@github.com:YOUR-NAME/feuerix.git
```

The script is equivalent to these commands:

```bash
git init -b main
git add -A
git commit -m "Initial version"
git remote add origin git@github.com:YOUR-NAME/feuerix.git
git push -u origin main
```

With the GitHub CLI it's even shorter: `gh repo create feuerix --private --source=. --push`

## Afterwards
* Open the **Actions tab**: the first CI run shows whether everything starts up. The code itself has already
  been checked by the included test suite – if errors still occur on the very first run, it's usually
  something environment-specific (e.g. secrets/environment variables in the Actions settings) – paste the
  log output of the red step here and we'll fix it in a targeted way.
* **Check in the migrations:** after the first start (`makemigrations`, see INSTALL.en.md), files appear
  under `apps/*/migrations/`. These **belong in the repository** (`git add apps/*/migrations && git
  commit`).
* **Never check in:** `.env`, `openslides/secrets/`, database dumps, backups. If passwords/keys are
  accidentally committed, change them immediately (just deleting the file isn't enough, the history
  remains).
* Recommended: protect the `main` branch (Settings › Branches), make changes via pull requests, releases
  with tags (`v0.1.0`), enable Dependabot for security updates (Settings › Code security).
* License: without a `LICENSE` file, the project is treated as "all rights reserved". For sharing with other
  clubs, deliberately choose a license (e.g. AGPL-3.0 or MIT).

## Can Claude commit directly?
It depends on the environment: in **Claude Code** (this CLI/IDE environment) with access to an already
set-up Git repository including push credentials, Claude can commit and push completely normally when you
explicitly ask it to – that's the usual way of working for ongoing changes to an existing repository. For
the **one-time initial setup** (creating the repository on GitHub, the very first push), however, it still
needs write access to that specific new repository; if that isn't available yet, or isn't connected to the
environment, handle that one step yourself as described above, via your own computer – after that, Claude
can keep working with the same repository as normal. In a plain chat environment without a connected
repository (e.g. claude.ai without a connector), committing directly is generally not possible.
