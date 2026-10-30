import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import type { Point2D, SimulationResult } from "../../lib/api";

interface Motion3DViewerProps {
  simulation: SimulationResult;
}

const LINK_WIDTH_MM = 10;
const LINK_THICKNESS_MM = 4;
const FRAME_MS = 40;

function toVector(point: Point2D): THREE.Vector3 {
  return new THREE.Vector3(point.x, point.y, 0);
}

export function Motion3DViewer({ simulation }: Motion3DViewerProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const applyFrameRef = useRef<((index: number) => void) | null>(null);
  const [status, setStatus] = useState<"ready" | "unavailable">("ready");
  const [playing, setPlaying] = useState(false);
  const [frame, setFrame] = useState(0);
  const samples = simulation.samples;
  const sampleCount = samples.length;

  useEffect(() => {
    setFrame(0);
    setPlaying(sampleCount > 1);
  }, [simulation, sampleCount]);

  useEffect(() => {
    if (!playing || sampleCount === 0) {
      return;
    }
    const timer = setInterval(() => {
      setFrame((current) => (current + 1) % sampleCount);
    }, FRAME_MS);
    return () => clearInterval(timer);
  }, [playing, sampleCount]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || sampleCount === 0) {
      return;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf8f9fb);
    const camera = new THREE.PerspectiveCamera(45, 1, 0.5, 20000);
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      setStatus("unavailable");
      return;
    }
    setStatus("ready");
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;

    scene.add(new THREE.AmbientLight(0xffffff, 0.8));
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.3);
    keyLight.position.set(1, 1, 1.4);
    scene.add(keyLight);
    const rimLight = new THREE.DirectionalLight(0xffffff, 0.45);
    rimLight.position.set(-1, -0.6, -1);
    scene.add(rimLight);

    const allPoints = samples.flatMap((sample) => [
      toVector(sample.ground_pivot_a),
      toVector(sample.ground_pivot_b),
      toVector(sample.crank_pin),
      toVector(sample.rocker_pin),
    ]);
    const bounds = new THREE.Box3().setFromPoints(allPoints);
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    const extent = Math.max(size.x, size.y, 1);

    const grid = new THREE.GridHelper(extent * 2.2, 22, 0xd7dde6, 0xe7ebf1);
    grid.rotation.x = Math.PI / 2;
    grid.position.set(center.x, center.y, -LINK_THICKNESS_MM * 1.6);
    scene.add(grid);

    const linkMaterial = new THREE.MeshStandardMaterial({
      color: 0x1f5eff,
      metalness: 0.15,
      roughness: 0.55,
    });
    const groundMaterial = new THREE.MeshStandardMaterial({
      color: 0x626b78,
      metalness: 0.2,
      roughness: 0.6,
    });
    const jointMaterial = new THREE.MeshStandardMaterial({
      color: 0x1b1f24,
      metalness: 0.3,
      roughness: 0.35,
    });

    const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
    const jointGeometry = new THREE.SphereGeometry(4.5, 20, 14);
    const pinGeometry = new THREE.CylinderGeometry(3, 3, LINK_THICKNESS_MM * 2.6, 20);

    const linkMeshes = {
      ground: new THREE.Mesh(boxGeometry, groundMaterial),
      crank: new THREE.Mesh(boxGeometry, linkMaterial),
      coupler: new THREE.Mesh(boxGeometry, linkMaterial),
      rocker: new THREE.Mesh(boxGeometry, linkMaterial),
    };
    Object.values(linkMeshes).forEach((mesh) => scene.add(mesh));

    const jointMeshes = {
      o2: new THREE.Mesh(jointGeometry, jointMaterial),
      o4: new THREE.Mesh(jointGeometry, jointMaterial),
      a: new THREE.Mesh(jointGeometry, jointMaterial),
      b: new THREE.Mesh(jointGeometry, jointMaterial),
    };
    Object.values(jointMeshes).forEach((joint) => scene.add(joint));
    const pin = new THREE.Mesh(pinGeometry, jointMaterial);
    pin.rotation.x = Math.PI / 2;
    scene.add(pin);

    const setLink = (mesh: THREE.Mesh, start: THREE.Vector3, end: THREE.Vector3) => {
      const mid = start.clone().add(end).multiplyScalar(0.5);
      mesh.position.copy(mid);
      mesh.rotation.set(0, 0, Math.atan2(end.y - start.y, end.x - start.x));
      mesh.scale.set(start.distanceTo(end), LINK_WIDTH_MM, LINK_THICKNESS_MM);
    };

    const applyFrame = (index: number) => {
      const sample = samples[Math.min(Math.max(index, 0), sampleCount - 1)];
      const o2 = toVector(sample.ground_pivot_a);
      const o4 = toVector(sample.ground_pivot_b);
      const a = toVector(sample.crank_pin);
      const b = toVector(sample.rocker_pin);
      setLink(linkMeshes.ground, o2, o4);
      setLink(linkMeshes.crank, o2, a);
      setLink(linkMeshes.coupler, a, b);
      setLink(linkMeshes.rocker, o4, b);
      jointMeshes.o2.position.copy(o2);
      jointMeshes.o4.position.copy(o4);
      jointMeshes.a.position.copy(a);
      jointMeshes.b.position.copy(b);
      pin.position.copy(a);
    };
    applyFrameRef.current = applyFrame;
    applyFrame(0);

    camera.near = extent / 100;
    camera.far = extent * 100;
    camera.position.set(
      center.x + extent * 0.75,
      center.y - extent * 0.85,
      extent * 1.35,
    );
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();

    const resize = () => {
      const width = mount.clientWidth || 520;
      const height = Math.max(240, Math.min(width * 0.6, 380));
      renderer.setSize(width, height, false);
      mount.style.height = `${height}px`;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    let raf = 0;
    const animate = () => {
      raf = window.requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      applyFrameRef.current = null;
      window.cancelAnimationFrame(raf);
      observer.disconnect();
      controls.dispose();
      boxGeometry.dispose();
      jointGeometry.dispose();
      pinGeometry.dispose();
      linkMaterial.dispose();
      groundMaterial.dispose();
      jointMaterial.dispose();
      renderer.dispose();
      if (renderer.domElement.parentElement === mount) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, [simulation, sampleCount, samples]);

  useEffect(() => {
    applyFrameRef.current?.(frame);
  }, [frame]);

  if (sampleCount === 0) {
    return <p className="empty-state">No computed motion trace for this run.</p>;
  }

  return (
    <div className="motion-viewer">
      <div
        ref={mountRef}
        className="motion-viewer-canvas"
        role="img"
        aria-label="Animated 3D mechanism built from the computed state trace"
      />
      {status === "unavailable" ? (
        <p className="notice notice-warning">
          <strong>3D view unavailable</strong>
          <span>This browser could not create a WebGL context.</span>
        </p>
      ) : null}
      <div className="playback-controls">
        <button type="button" onClick={() => setPlaying((value) => !value)}>
          {playing ? "Pause" : "Play"}
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(sampleCount - 1, 0)}
          value={Math.min(frame, sampleCount - 1)}
          onChange={(event) => {
            setPlaying(false);
            setFrame(Number(event.target.value));
          }}
          aria-label="Scrub through the computed motion"
        />
        <span className="playback-readout">
          θ = {samples[Math.min(frame, sampleCount - 1)].input_angle_deg.toFixed(1)}°
        </span>
      </div>
    </div>
  );
}
