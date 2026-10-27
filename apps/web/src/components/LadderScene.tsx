"use client";

// The sign-in scene: five fixed-deposit receipts climbing the Trust Ladder, one sheet per level
// (declared, read from the scan, checked by an officer, attested by the bank, live with the bank).
// The two bank levels carry the hue and a seal. Three.js is loaded only on this screen. With
// reduced motion the sheets are drawn once, already in place; without WebGL nothing is drawn and
// the level list beside the scene still says the same thing.

import { useEffect, useRef, useState } from "react";

type Palette = { paper: string; ink: string; faint: string; hue: string; ground: string };

function readPalette(el: HTMLElement): Palette {
  const css = getComputedStyle(el);
  const v = (name: string) => css.getPropertyValue(name).trim();
  return { paper: v("--surface"), ink: v("--text"), faint: v("--chart-muted"), hue: v("--hue"), ground: v("--frame") };
}

/** One receipt face: a header rule, a title bar, field rows drawn as bars (no invented values),
 *  and, on the bank levels, a round seal in the hue. */
function receiptTexture(p: Palette, level: number, labels: string[]): HTMLCanvasElement {
  const w = 768;
  const h = 512;
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const g = c.getContext("2d")!;
  g.fillStyle = p.paper;
  g.fillRect(0, 0, w, h);
  const bank = level >= 3;
  g.fillStyle = bank ? p.hue : p.ink;
  g.fillRect(0, 0, w, 14);
  g.fillStyle = p.ink;
  g.font = "600 30px 'IBM Plex Sans', system-ui, sans-serif";
  g.fillText(labels[0], 44, 78);
  g.fillStyle = p.faint;
  g.font = "400 22px 'IBM Plex Sans', system-ui, sans-serif";
  g.fillText(labels[1 + level], 44, 116);
  // field rows: caption bar + value bar; rows the level has confirmed are drawn in ink
  const rows = [0.62, 0.48, 0.7, 0.4, 0.55];
  rows.forEach((len, i) => {
    const y = 168 + i * 56;
    g.fillStyle = p.faint;
    g.globalAlpha = 0.55;
    g.fillRect(44, y, 150, 14);
    g.globalAlpha = 1;
    g.fillStyle = i <= level ? (bank ? p.hue : p.ink) : p.faint;
    g.fillRect(228, y - 4, (w - 300) * len, 22);
  });
  if (bank) {
    const cx = w - 128;
    const cy = h - 118;
    g.strokeStyle = p.hue;
    g.lineWidth = 8;
    g.beginPath();
    g.arc(cx, cy, 64, 0, Math.PI * 2);
    g.stroke();
    g.lineWidth = 3;
    g.beginPath();
    g.arc(cx, cy, 50, 0, Math.PI * 2);
    g.stroke();
    g.lineWidth = 10;
    g.lineCap = "round";
    g.lineJoin = "round";
    g.beginPath();
    g.moveTo(cx - 26, cy + 2);
    g.lineTo(cx - 6, cy + 22);
    g.lineTo(cx + 28, cy - 18);
    g.stroke();
  }
  return c;
}

export function LadderScene({ labels }: { labels: string[] }) {
  const host = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let disposed = false;
    let cleanup = () => {};

    import("three").then((THREE) => {
      if (disposed) return;
      const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      let renderer: InstanceType<typeof THREE.WebGLRenderer>;
      try {
        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
      } catch {
        setFailed(true);
        return;
      }
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.NoToneMapping;
      el.appendChild(renderer.domElement);
      renderer.domElement.setAttribute("aria-hidden", "true");

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
      camera.position.set(0, 2.2, 11);
      camera.lookAt(0, 0.3, 0);

      const ambient = new THREE.HemisphereLight(0xffffff, 0xe8edf2, 2.4);
      scene.add(ambient);
      const sun = new THREE.DirectionalLight(0xffffff, 1.4);
      sun.position.set(-3.5, 7, 5);
      sun.castShadow = true;
      sun.shadow.mapSize.set(1024, 1024);
      sun.shadow.camera.left = -6;
      sun.shadow.camera.right = 6;
      sun.shadow.camera.top = 6;
      sun.shadow.camera.bottom = -6;
      sun.shadow.radius = 6;
      scene.add(sun);

      const floor = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), new THREE.ShadowMaterial({ opacity: 0.12 }));
      floor.rotation.x = -Math.PI / 2;
      floor.position.y = -1.35;
      floor.receiveShadow = true;
      scene.add(floor);

      const group = new THREE.Group();
      scene.add(group);

      const geometry = new THREE.BoxGeometry(2.4, 1.6, 0.025);
      type Sheet = { mesh: InstanceType<typeof THREE.Mesh>; face: InstanceType<typeof THREE.CanvasTexture>; edge: InstanceType<typeof THREE.MeshStandardMaterial>; front: InstanceType<typeof THREE.MeshStandardMaterial>; home: InstanceType<typeof THREE.Vector3>; delay: number };
      const sheets: Sheet[] = [];

      const paint = () => {
        const p = readPalette(document.documentElement);
        sheets.forEach((s, level) => {
          const canvas = receiptTexture(p, level, labels);
          s.face.image = canvas;
          s.face.needsUpdate = true;
          s.edge.color.set(p.paper);
        });
        const dark = document.documentElement.dataset.theme === "dark";
        (floor.material as InstanceType<typeof THREE.ShadowMaterial>).opacity = dark ? 0.5 : 0.12;
        ambient.intensity = dark ? 1.1 : 2.4;
      };

      for (let level = 0; level < 5; level++) {
        const face = new THREE.CanvasTexture(document.createElement("canvas"));
        face.colorSpace = THREE.SRGBColorSpace;
        face.anisotropy = 4;
        const edge = new THREE.MeshStandardMaterial({ roughness: 0.9 });
        const front = new THREE.MeshStandardMaterial({ map: face, roughness: 0.85 });
        const mesh = new THREE.Mesh(geometry, [edge, edge, edge, edge, front, edge]);
        mesh.castShadow = true;
        const home = new THREE.Vector3(-2.1 + level * 1.05, -0.95 + level * 0.52, 1.1 - level * 0.55);
        mesh.position.copy(home);
        mesh.rotation.set(-0.22, 0.34, 0.02);
        group.add(mesh);
        sheets.push({ mesh, face, edge, front, home, delay: 0.18 * level });
      }
      paint();

      const resize = () => {
        const { width, height } = el.getBoundingClientRect();
        if (!width || !height) return;
        renderer.setSize(width, height, false);
        renderer.domElement.style.width = "100%";
        renderer.domElement.style.height = "100%";
        camera.aspect = width / height;
        // keep the whole flight in view on narrow screens
        camera.position.z = width / height < 1 ? 15 : width / height < 1.25 ? 12.5 : 11;
        camera.updateProjectionMatrix();
      };
      const ro = new ResizeObserver(() => {
        resize();
        if (reduced) renderer.render(scene, camera);
      });
      ro.observe(el);
      resize();

      const themeWatch = new MutationObserver(() => {
        paint();
        if (reduced) renderer.render(scene, camera);
      });
      themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

      const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
      const onMove = (e: PointerEvent) => {
        const r = el.getBoundingClientRect();
        pointer.tx = ((e.clientX - r.left) / r.width - 0.5) * 2;
        pointer.ty = ((e.clientY - r.top) / r.height - 0.5) * 2;
      };
      window.addEventListener("pointermove", onMove, { passive: true });

      const ease = (t: number) => 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 4);
      let raf = 0;
      let visible = true;
      const start = performance.now();
      const frame = (now: number) => {
        const t = (now - start) / 1000;
        pointer.x += (pointer.tx - pointer.x) * 0.05;
        pointer.y += (pointer.ty - pointer.y) * 0.05;
        group.rotation.y = pointer.x * 0.16;
        group.rotation.x = pointer.y * 0.06;
        sheets.forEach((s, i) => {
          const k = ease((t - s.delay) / 1.1);
          s.mesh.position.set(s.home.x, s.home.y - (1 - k) * 2.2 + Math.sin(t * 0.9 + i * 0.8) * 0.035 * k, s.home.z + (1 - k) * 1.5);
          s.mesh.rotation.z = 0.02 + (1 - k) * -0.35;
          const scale = 0.6 + 0.4 * k;
          s.mesh.scale.setScalar(scale);
        });
        renderer.render(scene, camera);
        if (visible) raf = requestAnimationFrame(frame);
      };

      if (reduced) {
        renderer.render(scene, camera);
      } else {
        raf = requestAnimationFrame(frame);
      }
      // stop drawing when the scene is off screen or the tab is hidden
      const io = new IntersectionObserver(([entry]) => {
        const next = entry.isIntersecting && !document.hidden;
        if (next && !visible && !reduced) raf = requestAnimationFrame(frame);
        visible = next;
      });
      io.observe(el);

      cleanup = () => {
        cancelAnimationFrame(raf);
        ro.disconnect();
        io.disconnect();
        themeWatch.disconnect();
        window.removeEventListener("pointermove", onMove);
        sheets.forEach((s) => {
          s.face.dispose();
          s.front.dispose();
          s.edge.dispose();
        });
        geometry.dispose();
        floor.geometry.dispose();
        (floor.material as InstanceType<typeof THREE.ShadowMaterial>).dispose();
        renderer.dispose();
        renderer.domElement.remove();
      };
    }).catch(() => setFailed(true));

    return () => {
      disposed = true;
      cleanup();
    };
  }, [labels]);

  return <div ref={host} className={`ladder-scene${failed ? " failed" : ""}`} />;
}
