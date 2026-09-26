# sora2looseload

`xinput1_4.dll` is the MIT-licensed loose-file loader from
https://github.com/lmaple0/sora2looseload.

- Source revision: `745cf903bee976b72ad84c200a71e9137d666261`
- Upstream base: `04e898e369e3019d5aa2cb13a7209de39c643a4a`
- Detours revision: `adb07604aa56508448b95bf037c2a6d0d3b6831a`
- Target: Steam build 25386012, `sora_2nd.exe` 1.3.2.0
- SHA-256: `e08a18068a482bb5d187a62023759c0e14ab69d76395b773ef0405d35e2ac8c7`

The included `LICENSE` applies to this loader. `DETOURS-LICENSE.md` preserves
the separate Microsoft copyright and MIT terms for the linked Detours revision.
Game fonts are never bundled: the application builds loose FNT/DDS files only
from the user's local game archives.
