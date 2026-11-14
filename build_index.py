"""Mirror libSceAmpr.sprx builds from quer3q/ampr-emu-ng releases into ./apr-emu
and write the builds.json that apr-emu-updater reads."""
import hashlib, json, os, re, sys, urllib.request

REPO = "quer3q/ampr-emu-ng"
OUT = "apr-emu"
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def _req(url):
    h = {"User-Agent": "ampr-ng-repo-sync", "Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = "Bearer " + TOKEN
    return urllib.request.Request(url, headers=h)


def fetch_json(url):
    with urllib.request.urlopen(_req(url), timeout=60) as r:
        return json.load(r)


def fetch_bin(url):
    with urllib.request.urlopen(_req(url), timeout=300) as r:
        return r.read()


def all_releases():
    rels, page = [], 1
    while True:
        chunk = fetch_json(f"https://api.github.com/repos/{REPO}/releases?per_page=100&page={page}")
        if not chunk:
            return rels
        rels += chunk
        page += 1


def main():
    os.makedirs(OUT, exist_ok=True)
    versions, keep, seen = [], {"builds.json"}, set()
    for rel in all_releases():  # API order: newest first
        if rel.get("draft") or rel.get("prerelease"):  # stable releases only
            continue
        version = re.sub(r"[^A-Za-z0-9._-]+", "-", rel["tag_name"].lstrip("vV"))
        if not version or version in seen:
            continue
        found = {}
        for a in rel.get("assets", []):
            n = a["name"]
            if not n.lower().endswith(".sprx"):
                continue
            if "debug" in n.lower():  # regular builds only
                continue
            kind = "release"
            if kind in found:
                print(f"warning: {version} has several {kind} .sprx assets; using {found[kind]['name']}")
                continue
            found[kind] = a
        builds = []
        for kind in ("release",):
            a = found.get(kind)
            if not a:
                continue
            fname = f"libSceAmpr.sprx-{version}" + ("-debug" if kind == "debug" else "")
            path = os.path.join(OUT, fname)
            want = (a.get("digest") or "").removeprefix("sha256:") or None
            data = None
            if os.path.isfile(path):
                data = open(path, "rb").read()
                if len(data) != a["size"] or (want and hashlib.sha256(data).hexdigest() != want):
                    data = None
            if data is None:
                data = fetch_bin(a["browser_download_url"])
                if len(data) != a["size"]:
                    sys.exit(f"size mismatch for {a['name']} ({version})")
                if want and hashlib.sha256(data).hexdigest() != want:
                    sys.exit(f"sha256 mismatch for {a['name']} ({version})")
                open(path, "wb").write(data)
            keep.add(fname)
            builds.append({"build": kind, "file": fname, "bytes": len(data),
                           "sha256": hashlib.sha256(data).hexdigest()})
        if builds:
            seen.add(version)
            versions.append({"version": version, "builds": builds})
    if not versions:
        sys.exit("no .sprx builds found; leaving repo unchanged")
    # No debug builds are published; point "debug" at the same version, as the
    # updater's own README example does when a version has no debug build.
    latest = {"release": versions[0]["version"], "debug": versions[0]["version"]}
    doc = {"builds": "apr-emu", "buildsVersion": 2,
           "repository": f"https://github.com/{REPO}",
           "latest": latest, "versions": versions}
    for f in os.listdir(OUT):
        if f not in keep:
            os.remove(os.path.join(OUT, f))
    with open(os.path.join(OUT, "builds.json"), "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print(f"{len(versions)} version(s); latest {latest}")


if __name__ == "__main__":
    main()
