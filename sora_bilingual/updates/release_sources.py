"""Mirror selection and bounded fallback; installation remains source-independent."""

import urllib.error

from sora_bilingual.updates.gitee_updates import GiteeClient
from sora_bilingual.updates.github_updates import GitHubClient
from sora_bilingual.updates.release_client import version_tuple

NETWORK_ERRORS = (OSError, ValueError, RuntimeError, urllib.error.URLError)


class ReleaseSources:
    def __init__(self, repository, current_version, *, github=None, gitee=None):
        # Both publishers use the same repository identity and unmodified manifest.
        self.clients = {
            "gitee": gitee or GiteeClient(repository),
            "github": github or GitHubClient(repository),
        }
        self.repository = repository
        self.current_version = version_tuple(current_version)
        self._metadata = {}

    def latest(self, cache=None):
        cache = cache or {}
        caches = dict(cache.get("sources", {}))
        # Migrate existing GitHub cache without mixing provider validators.
        if cache.get("repository") == self.repository:
            caches["github"] = cache
        self._metadata.clear()
        candidates = []
        errors = []
        for source, client in self.clients.items():
            try:
                release, updated = client.latest(caches.get(source))
                caches[source] = updated
                if release is None:
                    continue
                version = version_tuple(release["tag_name"])
                selected = {**release, "_source": source}
                # An incomplete mirror must not stop fallback to GitHub.
                if version > self.current_version:
                    self._metadata[source, release["tag_name"]] = client.metadata(release)
                    return selected, {"sources": caches}
                candidates.append((version, selected))
            except NETWORK_ERRORS as exc:
                errors.append(type(exc).__name__)
        if candidates:
            return max(candidates, key=lambda item: item[0])[1], {"sources": caches}
        if errors:
            # Don't log signed redirect URLs or pretend an offline cache is fresh.
            raise RuntimeError("国内与备用更新源检查未完成：" + ", ".join(errors))
        return None, {"sources": caches}

    def metadata(self, release):
        source = release["_source"]
        key = source, release["tag_name"]
        if key not in self._metadata:
            self._metadata[key] = self.clients[source].metadata(release)
        meta, asset = self._metadata[key]
        return meta, ({**asset, "_source": source, "_tag": release["tag_name"]} if asset else None)

    def history(self):
        releases = {}
        succeeded = False
        for source, client in self.clients.items():
            try:
                for release in client.history():
                    releases.setdefault(
                        version_tuple(release["tag_name"]), {**release, "_source": source}
                    )
                succeeded = True
            except NETWORK_ERRORS:
                continue
        if not succeeded:
            raise RuntimeError("历史版本检查未完成，请稍后重试")
        return [releases[v] for v in sorted(releases, reverse=True)]

    def release(self, tag):
        # Resolve the confirmed tag afresh; a pruned/incomplete mirror can fall
        # back to the same stable GitHub release, never to latest.
        version_tuple(tag)
        for source, client in self.clients.items():
            try:
                release = client.release(tag)
                self._metadata[source, tag] = client.metadata(release)
                return {**release, "_source": source}
            except NETWORK_ERRORS:
                continue
        raise RuntimeError("所选版本暂不可用，请稍后重试或查看发行页面")

    def component_asset(self, release, descriptor):
        source = release["_source"]
        return {
            **self.clients[source].component_asset(release, descriptor),
            "_source": source,
            "_tag": release["tag_name"],
        }

    def download(self, asset, descriptor, path, progress=lambda _: None):
        source = asset["_source"]
        try:
            self.clients[source].download(asset, descriptor, path, progress)
            return
        except NETWORK_ERRORS:
            pass
        other = "github" if source == "gitee" else "gitee"
        client = self.clients[other]
        # Keep the selected version and SHA-256 fixed during failover; never
        # substitute a different release or accept bytes from a partial upload.
        tag = asset.get("_tag", "v" + descriptor.get("version", ""))
        version_tuple(tag)
        name = descriptor["asset"]
        if "/" in name or "\\" in name:
            raise ValueError("无效附件名")
        alternate = {
            "browser_download_url": f"https://{client.host}/{self.repository}/releases/download/{tag}/{name}"
        }
        client.download(alternate, descriptor, path, progress)
