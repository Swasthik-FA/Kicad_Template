#!/usr/bin/env python3
"""
make_offline_viewer.py
======================

Builds a single self-contained HTML page that renders the project's GLB
model in any browser by double-clicking it from disk — no server, no
GitHub Pages, no setup. The GLB is base64-embedded into the HTML and
parsed by three.js's classic (non-module) build, which is allowed to
load over file:// from a CDN.

Usage
-----
    python config/scripts/make_offline_viewer.py
        # auto-discovers HTML/3d/*.glb, writes HTML/pcb-3d-offline.html

    python config/scripts/make_offline_viewer.py \
        --glb HTML/3d/Nano-Board-rev-2.glb \
        --output HTML/pcb-3d-offline.html \
        --title "Nano-Board-rev-2"

The output is a single .html file ~4/3 the size of the GLB (base64
overhead). Open it on any PC by double-click — works on file://.

This script is meant to be run on demand (e.g. before sending the
project to a reviewer who can't run a local server). It is *not*
wired into CI by default to avoid bloating the repo's git history.
"""

from __future__ import annotations

import argparse
import base64
import html
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------
# Uses three.js r149 (last release with the classic non-module
# `examples/js/` builds for GLTFLoader + OrbitControls). All JS is
# loaded from jsDelivr over HTTPS, which browsers permit even when the
# parent page is on file://.
# ---------------------------------------------------------------------------

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — 3D viewer (offline)</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body {
    margin: 0;
    background: #0A0E1A;
    color: #E6E9F2;
    font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif;
    overflow: hidden;
    height: 100vh;
  }
  body {
    background-image:
      radial-gradient(820px 620px at 8% -12%, rgba(99,102,241,0.42), transparent 60%),
      radial-gradient(680px 520px at 96% -4%, rgba(14,165,233,0.32), transparent 65%),
      radial-gradient(720px 580px at 88% 105%, rgba(236,72,153,0.28), transparent 62%),
      radial-gradient(760px 600px at 4% 110%, rgba(168,85,247,0.34), transparent 60%);
  }
  #viewer { width: 100vw; height: 100vh; display: block; }
  .hud {
    position: fixed; top: 16px; left: 16px;
    background: rgba(22,28,45,0.55);
    backdrop-filter: blur(22px) saturate(180%);
    -webkit-backdrop-filter: blur(22px) saturate(180%);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px; padding: 14px 18px;
    font-size: 13px; line-height: 1.5; max-width: 360px;
    box-shadow: 0 8px 24px rgba(0,0,0,.30);
  }
  .hud h1 {
    margin: 0 0 6px; font-size: 15px; font-weight: 700;
    background: linear-gradient(90deg,#818CF8,#6366F1,#E6E9F2);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent; color: transparent;
  }
  .hud .muted { color: #94A0B8; font-size: 12px; }
  .loader {
    position: fixed; inset: 0;
    display: flex; align-items: center; justify-content: center;
    flex-direction: column; gap: 12px; color: #94A0B8;
    pointer-events: none; transition: opacity .3s ease;
  }
  .spinner {
    width: 36px; height: 36px;
    border: 3px solid rgba(255,255,255,0.10);
    border-top-color: #818CF8;
    border-radius: 50%;
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .err {
    position: fixed; inset: 0;
    display: none; align-items: center; justify-content: center;
    text-align: center; padding: 32px; color: #F87171;
    font-size: 14px;
  }
</style>
</head>
<body>
  <canvas id="viewer"></canvas>
  <div class="hud">
    <h1>__TITLE__ — 3D model</h1>
    <div class="muted">
      Drag to rotate · scroll / pinch to zoom · right-drag to pan
    </div>
  </div>
  <div class="loader" id="loader">
    <div class="spinner"></div>
    <div>Decoding embedded model…</div>
  </div>
  <div class="err" id="err"></div>

  <!-- Embedded GLB — base64 of the entire binary glTF, parsed at startup -->
  <script id="glb-data" type="application/octet-stream">__GLB_BASE64__</script>

  <!-- three.js r149 classic IIFE builds (load fine over file:// from CDN) -->
  <script src="https://cdn.jsdelivr.net/npm/three@0.149.0/build/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.149.0/examples/js/loaders/GLTFLoader.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.149.0/examples/js/controls/OrbitControls.js"></script>
  <script>
  (function () {
    var loader = document.getElementById('loader');
    var err = document.getElementById('err');
    function fail(msg) {
      loader.style.display = 'none';
      err.style.display = 'flex';
      err.textContent = msg;
    }

    if (typeof THREE === 'undefined' || !THREE.GLTFLoader || !THREE.OrbitControls) {
      fail('Failed to load three.js from the CDN — check your internet ' +
           'connection. (The 3D viewer needs a one-time download of the ' +
           'three.js library; the model itself is embedded in this file.)');
      return;
    }

    // Decode base64 GLB into an ArrayBuffer.
    var b64 = document.getElementById('glb-data').textContent.trim();
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);

    var canvas = document.getElementById('viewer');
    var renderer = new THREE.WebGLRenderer({
      canvas: canvas, antialias: true, alpha: true
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight, false);
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    var scene = new THREE.Scene();

    var camera = new THREE.PerspectiveCamera(
      45, window.innerWidth / window.innerHeight, 0.01, 1000
    );
    camera.position.set(0, 0.05, 0.18);

    // Lighting — soft key + fill + back, plus environment ambient
    scene.add(new THREE.HemisphereLight(0xffffff, 0x0B0F19, 0.55));
    var key = new THREE.DirectionalLight(0xffffff, 1.2);
    key.position.set(0.5, 1, 0.7);
    scene.add(key);
    var fill = new THREE.DirectionalLight(0xc8d2ff, 0.4);
    fill.position.set(-0.7, 0.4, -0.4);
    scene.add(fill);
    var back = new THREE.DirectionalLight(0xffd9b3, 0.3);
    back.position.set(0, 0.5, -1);
    scene.add(back);

    var controls = new THREE.OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.rotateSpeed = 0.9;
    controls.zoomSpeed = 0.9;
    controls.panSpeed = 0.6;

    var gltfLoader = new THREE.GLTFLoader();
    gltfLoader.parse(
      bytes.buffer, '',
      function (gltf) {
        var model = gltf.scene || gltf.scenes[0];
        scene.add(model);

        // Center on origin and frame the camera around the model.
        var box = new THREE.Box3().setFromObject(model);
        var size = box.getSize(new THREE.Vector3()).length();
        var center = box.getCenter(new THREE.Vector3());
        model.position.sub(center);
        controls.target.set(0, 0, 0);

        camera.near = size / 100;
        camera.far  = size * 100;
        camera.updateProjectionMatrix();
        camera.position.copy(new THREE.Vector3(0.7, 0.5, 1.0).normalize().multiplyScalar(size * 1.1));
        controls.maxDistance = size * 5;
        controls.minDistance = size * 0.05;
        controls.update();

        loader.style.opacity = '0';
        setTimeout(function () { loader.style.display = 'none'; }, 350);
      },
      function (e) {
        console.error(e);
        fail('Failed to parse the embedded model: ' + (e && e.message ? e.message : e));
      }
    );

    function tick() {
      controls.update();
      renderer.render(scene, camera);
      requestAnimationFrame(tick);
    }
    tick();

    window.addEventListener('resize', function () {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight, false);
    });
  })();
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--glb", type=Path,
                    help="Path to the GLB. Defaults to the first HTML/3d/*.glb found.")
    ap.add_argument("--output", type=Path,
                    default=Path("HTML/pcb-3d-offline.html"),
                    help="Output HTML path (default: HTML/pcb-3d-offline.html).")
    ap.add_argument("--title", type=str, default="",
                    help="Title shown in the HUD. Defaults to the GLB stem.")
    args = ap.parse_args()

    glb_path: Path | None = args.glb
    if glb_path is None:
        candidates = sorted(Path("HTML/3d").glob("*.glb"))
        if not candidates:
            print("error: no GLB found under HTML/3d/. "
                  "Run the CI workflow once (or pass --glb explicitly).",
                  file=sys.stderr)
            return 1
        glb_path = candidates[0]

    if not glb_path.exists():
        print(f"error: GLB not found: {glb_path}", file=sys.stderr)
        return 1

    title = args.title or glb_path.stem
    glb_bytes = glb_path.read_bytes()
    glb_b64 = base64.b64encode(glb_bytes).decode("ascii")

    html_doc = (TEMPLATE
                .replace("__TITLE__", html.escape(title))
                .replace("__GLB_BASE64__", glb_b64))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_doc, encoding="utf-8")

    in_mb = len(glb_bytes) / (1024 * 1024)
    out_mb = args.output.stat().st_size / (1024 * 1024)
    print(f"Wrote {args.output}")
    print(f"  GLB:  {glb_path} ({in_mb:.1f} MB)")
    print(f"  HTML: {out_mb:.1f} MB (base64 + scaffolding)")
    print(f"\nDouble-click {args.output} on any PC. Internet is needed once "
          f"to fetch three.js from the CDN; the model itself is embedded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
