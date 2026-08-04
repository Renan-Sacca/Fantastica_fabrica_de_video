"""Probe: descobre qual combinação de flags/env faz o Chromium usar a GPU
(Mesa d3d12 via /dev/dxg no WSL2) em vez do SwiftShader.

Uso: docker exec -e <VARS> fabrica-worker python renderers/music_visualizer/gpu_probe.py
"""
import asyncio, os, sys

DATA_URL = (
    "data:text/html,"
    "<canvas id=c></canvas><script>"
    "var gl=document.getElementById('c').getContext('webgl2');"
    "var d=gl.getExtension('WEBGL_debug_renderer_info');"
    "window.R=d?gl.getParameter(d.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);"
    "window.V=d?gl.getParameter(d.UNMASKED_VENDOR_WEBGL):gl.getParameter(gl.VENDOR);"
    "</script>"
)

# Conjuntos de flags para testar (rotulados)
IP = ["--in-process-gpu", "--disable-gpu-sandbox"]
FLAG_SETS = {
    "angle-gl": ["--use-gl=angle", "--use-angle=gl"],
    "angle-gl-ip": ["--use-gl=angle", "--use-angle=gl"] + IP,
    "egl-ip": ["--use-gl=egl"] + IP,
    "angle-gl-newhl": ["--use-gl=angle", "--use-angle=gl", "--headless=new"] + IP,
}

COMMON = [
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
    "--ignore-gpu-blocklist", "--enable-gpu-rasterization",
    "--enable-webgl", "--enable-webgl2",
    "--enable-features=Vulkan,UseSkiaRenderer",
]


async def probe(label, flags):
    from playwright.async_api import async_playwright
    headless = os.environ.get("HEADFUL") != "1" and "--headless=new" not in flags
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=headless, args=COMMON + flags)
            pg = await b.new_page()
            await pg.goto(DATA_URL)
            await pg.wait_for_timeout(400)
            r = await pg.evaluate("window.R || '(no webgl2)'")
            v = await pg.evaluate("window.V || ''")
            await b.close()
            sw = "swiftshader" in str(r).lower() or "llvmpipe" in str(r).lower()
            tag = "SOFTWARE" if sw else ">>> GPU <<<"
            print(f"[{label:14}] {tag}  R={r} | V={v}")
    except Exception as e:
        print(f"[{label:14}] ERRO: {e}")


async def main():
    env_dump = {k: os.environ[k] for k in os.environ
                if k.startswith(("MESA", "GALLIUM", "LIBGL", "EGL", "__GLX", "ANGLE"))}
    print(f"ENV relevante: {env_dump}")
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for label, flags in FLAG_SETS.items():
        if only and label != only:
            continue
        await probe(label, flags)


if __name__ == "__main__":
    asyncio.run(main())
