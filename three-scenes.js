/* three.js scenes: voxel globe body and the Pentagon-area open-shop schematic.
   three.js loads lazily from jsDelivr only when a scene is about to be shown; without WebGL
   (or if the download fails) the page keeps its 2D canvas globe and the text counts. */
(() => {
  'use strict';
  const THREE_URL = 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.min.js';
  let threePromise = null;
  function webglOK() {
    try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); }
    catch { return false; }
  }
  function load() {
    if (!webglOK()) return Promise.reject(new Error('no webgl'));
    threePromise = threePromise || import(THREE_URL);
    return threePromise;
  }

  // ── Globe body ─────────────────────────────────────────────
  // Same orientation as the 2D projection in index.html (lam0, phi0, zoom, radius baseR px),
  // so the 2D overlay's labels, region rings and fire dots stay exactly on top.
  function globe(THREE, canvas, data) {
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
    camera.position.set(0, 0, 4);
    const earth = new THREE.Group();
    scene.add(earth);
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const sun = new THREE.DirectionalLight(0xffffff, 1.15);
    sun.position.set(-2, 1.5, 3);
    scene.add(sun);

    // Deep-ocean ball under the voxels so gaps between tiles never show through.
    earth.add(new THREE.Mesh(new THREE.SphereGeometry(0.985, 64, 48),
      new THREE.MeshLambertMaterial({ color: 0x0c3a68 })));

    const place = (lon, lat, r, obj) => {
      const l = lon * Math.PI / 180, p = lat * Math.PI / 180;
      obj.position.set(r * Math.cos(p) * Math.sin(l), r * Math.sin(p), r * Math.cos(p) * Math.cos(l));
      obj.lookAt(0, 0, 0);
    };
    function voxels(points, palette, size, depth, lift, shade) {
      const n = points.length / 3;
      const mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(size, size, depth),
        new THREE.MeshLambertMaterial(), n);
      const dummy = new THREE.Object3D(), color = new THREE.Color();
      for (let i = 0; i < n; i++) {
        const lon = points[i * 3] / 10, lat = points[i * 3 + 1] / 10, rgb = palette[points[i * 3 + 2]] || palette[0];
        // Stable per-tile noise keeps the pixel-art texture of the 2D globe.
        const noise = (((points[i * 3] * 13) ^ (points[i * 3 + 1] * 29)) & 255) / 255;
        place(lon, lat, lift, dummy);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
        const k = shade * (0.9 + 0.16 * noise);
        color.setRGB(rgb[0] / 255 * k, rgb[1] / 255 * k, rgb[2] / 255 * k, THREE.SRGBColorSpace);
        mesh.setColorAt(i, color);
      }
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      return mesh;
    }
    // Ocean tiles sit flush; land is a raised voxel layer (2.2° grid, ~0.038 rad per tile).
    earth.add(voxels(data.ocean, data.oceanPalette, 0.05, 0.012, 0.995, 1.0));
    earth.add(voxels(data.land, data.landPalette, 0.046, 0.03, 1.012, 0.95));

    // The atmosphere halo stays on the 2D overlay, drawn with the labels.

    let width = 0, height = 0, radius = 1;
    return {
      resize(w, h, baseR, dpr) {
        width = w; height = h; radius = baseR;
        renderer.setPixelRatio(dpr);
        renderer.setSize(w, h, false);
      },
      render(lam0, phi0, zoom) {
        if (!width || !height) return;
        const s = radius * zoom;              // pixels per unit radius
        camera.left = -width / 2 / s; camera.right = width / 2 / s;
        camera.top = height / 2 / s; camera.bottom = -height / 2 / s;
        camera.updateProjectionMatrix();
        earth.rotation.set(phi0, -lam0, 0, 'XYZ');
        renderer.render(scene, camera);
      },
    };
  }

  // ── Pentagon-area open-shop schematic ─────────────────────
  // Approximate venue positions (Arlington, VA); this is a schematic, not a map.
  const PENTAGON = [38.8719, -77.0563];
  const VENUES = [
    { kind: 'pizza', name: 'We, The Pizza', at: [38.8545, -77.0497] },
    { kind: 'pizza', name: 'Pizzato Pizza', at: [38.8795, -77.0905] },
    { kind: 'pizza', name: 'Papa Johns Pizza', at: [38.8600, -77.0960] },
    { kind: 'pizza', name: "Domino's Pizza (Pentagon Closest)", at: [38.8625, -77.0855] },
    { kind: 'pizza', name: 'Extreme Pizza', at: [38.8615, -77.0530] },
    { kind: 'pizza', name: 'District Pizza Palace', at: [38.8530, -77.0532] },
    { kind: 'bar', name: 'Sine Irish Pub', at: [38.8635, -77.0630] },
    { kind: 'bar', name: "Freddie's Beach Bar", at: [38.8535, -77.0510] },
    { kind: 'bar', name: 'Highline RxR', at: [38.8555, -77.0490] },
    { kind: 'bar', name: "Ireland's Four Courts", at: [38.8915, -77.0855] },
  ];
  const COLORS = { pizza: 0xe3a83f, bar: 0x7eb0e0, closed: 0x2a313b, unknown: 0x4a5462 };

  function pentagonShape(THREE, r) {
    const s = new THREE.Shape();
    for (let i = 0; i < 5; i++) {
      const a = Math.PI / 2 + i * 2 * Math.PI / 5;
      const x = Math.cos(a) * r, y = Math.sin(a) * r;
      if (i) s.lineTo(x, y); else s.moveTo(x, y);
    }
    s.closePath();
    return s;
  }

  function pentagon(THREE, canvas) {
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 2, 0.1, 100);
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.0);
    sun.position.set(4, 8, 5);
    scene.add(sun);
    const world = new THREE.Group();
    scene.add(world);

    const ground = new THREE.Mesh(new THREE.CircleGeometry(3.1, 64), new THREE.MeshLambertMaterial({ color: 0x111821 }));
    ground.rotation.x = -Math.PI / 2;
    world.add(ground);
    const grid = new THREE.PolarGridHelper(3, 8, 4, 64, 0x2c3a49, 0x1f2a36);
    grid.position.y = 0.002;
    world.add(grid);

    // The Pentagon: five-sided ring with a courtyard.
    const outer = pentagonShape(THREE, 0.62);
    outer.holes.push(pentagonShape(THREE, 0.3));
    const building = new THREE.Mesh(new THREE.ExtrudeGeometry(outer, { depth: 0.14, bevelEnabled: false }),
      new THREE.MeshLambertMaterial({ color: 0x9aa6b4 }));
    building.rotation.x = -Math.PI / 2;
    world.add(building);

    // 1 km ≈ 0.75 units around the Pentagon (rings ≈ 1 km apart); x east, z south.
    const km = 0.75, toXZ = ([lat, lng]) => [(lng - PENTAGON[1]) * 86.6 * km, -(lat - PENTAGON[0]) * 111.2 * km];
    const markers = VENUES.map(v => {
      const [x, z] = toXZ(v.at);
      const mat = new THREE.MeshLambertMaterial({ color: COLORS.unknown });
      const geo = v.kind === 'pizza' ? new THREE.CylinderGeometry(0.14, 0.14, 1, 6) : new THREE.BoxGeometry(0.22, 1, 0.22);
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(x, 0.05, z);
      mesh.scale.y = 0.1;
      world.add(mesh);
      return { ...v, mesh, mat };
    });

    let width = 0, height = 0, spin = 0;
    return {
      resize(w, h, dpr) {
        width = w; height = h;
        renderer.setPixelRatio(dpr);
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        camera.position.set(0, w < 480 ? 5 : 4.4, w < 480 ? 5.6 : 6.4);
        camera.lookAt(0, 0.2, 0);
        camera.updateProjectionMatrix();
      },
      // states: name → {state:'open'|'closed'|'unknown', level:0..100|null}
      update(states) {
        for (const m of markers) {
          const s = states[m.name] || { state: 'unknown' };
          const open = s.state === 'open';
          m.mat.color.setHex(open ? COLORS[m.kind] : s.state === 'closed' ? COLORS.closed : COLORS.unknown);
          m.mat.emissive.setHex(open ? COLORS[m.kind] : 0x000000);
          m.mat.emissiveIntensity = open ? 0.35 : 0;
          const h = open ? 0.3 + 1.3 * (typeof s.level === 'number' ? s.level / 100 : 0.4) : s.state === 'closed' ? 0.06 : 0.14;
          m.mesh.scale.y = h;
          m.mesh.position.y = h / 2;
        }
      },
      render(dt) {
        if (!width) return;
        spin += dt;
        world.rotation.y = spin;
        renderer.render(scene, camera);
      },
      venues: VENUES,
    };
  }

  window.WarhubThree = { load, globe, pentagon, webglOK, VENUES };
})();
