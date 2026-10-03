"""Anonymous Gitee release discovery; previews are never stable updates."""

from sora_bilingual.updates.release_client import GITEE_HOSTS, ReleaseClient


class GiteeClient(ReleaseClient):
    host = "gitee.com"
    hosts = GITEE_HOSTS
    headers = {"Accept": "application/json"}
    component_only = True

    @property
    def releases_url(self):
        return f"https://gitee.com/api/v5/repos/{self.repository}/releases"

    def latest(self, cache=None):
        # Gitee /latest includes prereleases. Read a bounded, descending list
        # instead; ETags from GitHub must never be sent to this source.
        stable = self.history()
        if not stable:
            return None, {}
        return self._with_assets(stable[0]), {}

    def release(self, tag):
        return self._with_assets(super().release(tag))

    def _with_assets(self, release):
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
        return release
