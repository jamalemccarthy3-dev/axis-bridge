# Third-party code in this folder

| File | Project | Version | Licence | Source | SHA-256 |
|---|---|---|---|---|---|
| `babylon.js` | Babylon.js | 9.30.0 | Apache-2.0 | https://cdn.babylonjs.com/babylon.js (downloaded once, then served locally) | `ff331103574d58a94e68353087721260628a4a6dd5521aa98949127bde73bbff` |

The dashboard loads this file from the NEXXUS server itself (`/vendor/babylon.js`), never from the internet. To update it, replace the file, check the
version, record the new SHA-256 here, and run `test_dashboard_offline.py`. Babylon.js is (c) its contributors and is used under the Apache License 2.0
(https://www.apache.org/licenses/LICENSE-2.0).

Note: the library contains URLs for OPTIONAL features it can use (default environment textures, VR controller models, extra loaders). The NEXXUS dashboard does
not use them; `test_dashboard_offline.py` verifies that the page makes no request to any other host.
