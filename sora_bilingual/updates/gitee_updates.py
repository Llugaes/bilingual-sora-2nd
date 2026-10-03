"""Anonymous Gitee release discovery; previews are never stable updates."""

from sora_bilingual.updates.release_client import GITEE_HOSTS, ReleaseClient, version_tuple


class GiteeClient(ReleaseClient):
    host = "gitee.com"
    hosts = GITEE_HOSTS
    headers = {"Accept": "application/json"}
    component_only = True

    def latest(self, cache=None):
        # Gitee /latest includes prereleases. Read a bounded, descending list
        # instead; ETags from GitHub must never be sent to this source.
        releases = self._json(
            f"https://gitee.com/api/v5/repos/{self.repository}/releases"
            "?direction=desc&per_page=100&page=1"
        )
        if not isinstance(releases, list):
            raise ValueError("Gitee 发行列表无效")
        stable = []
        for release in releases:
            if not isinstance(release, dict) or release.get("prerelease") or release.get("draft"):
                continue
            try:
                version = version_tuple(release.get("tag_name"))
            except ValueError:
                continue
            stable.append((version, release))
        if not stable:
            return None, {}
        release = max(stable, key=lambda item: item[0])[1]
        release_id = release.get("id")
        if type(release_id) is not int or release_id <= 0:
            raise ValueError("Gitee 发行 ID 无效")
        assets = self._json(
            f"https://gitee.com/api/v5/repos/{self.repository}/releases/"
            f"{release_id}/attach_files?per_page=100&page=1"
        )
        if not isinstance(assets, list) or len(assets) >= 100:
            raise ValueError("Gitee 发行附件列表不完整")
        release = {**release, "assets": [{**item, "state": "uploaded"} for item in assets]}
        return release, {}
