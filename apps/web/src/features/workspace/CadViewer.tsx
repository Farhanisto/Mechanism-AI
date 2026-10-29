import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

interface CadViewerProps {
  url: string;
}

export function CadViewer({ url }: CadViewerProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error" | "unavailable">(
    "loading",
  );

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) {
      return;
    }
    setStatus("loading");
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
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;

    scene.add(new THREE.AmbientLight(0xffffff, 0.75));
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.4);
    keyLight.position.set(1, 1, 1);
    scene.add(keyLight);
    const rimLight = new THREE.DirectionalLight(0xffffff, 0.5);
    rimLight.position.set(-1, -1, 0.6);
    scene.add(rimLight);

    let disposed = false;
    let mesh: THREE.Mesh | null = null;
    const loader = new STLLoader();
    loader.load(
      url,
      (geometry) => {
        if (disposed) {
          geometry.dispose();
          return;
        }
        geometry.computeVertexNormals();
        mesh = new THREE.Mesh(
          geometry,
          new THREE.MeshStandardMaterial({
            color: 0x1f5eff,
            metalness: 0.15,
            roughness: 0.55,
          }),
        );
        geometry.computeBoundingBox();
        const bounds = geometry.boundingBox;
        if (bounds) {
          const center = bounds.getCenter(new THREE.Vector3());
          const size = bounds.getSize(new THREE.Vector3());
          const maxDimension = Math.max(size.x, size.y, size.z, 1);
          mesh.position.sub(center);
          camera.near = maxDimension / 100;
          camera.far = maxDimension * 100;
          camera.position.set(maxDimension * 1.2, maxDimension * 0.9, maxDimension * 1.4);
          camera.updateProjectionMatrix();
        }
        scene.add(mesh);
        controls.target.set(0, 0, 0);
        controls.update();
        setStatus("ready");
      },
      undefined,
      () => {
        if (!disposed) {
          setStatus("error");
        }
      },
    );

    const resize = () => {
      const width = mount.clientWidth || 480;
      const height = mount.clientHeight || 320;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    let frame = 0;
    const animate = () => {
      frame = window.requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      disposed = true;
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      if (mesh) {
        mesh.geometry.dispose();
        (mesh.material as THREE.Material).dispose();
      }
      renderer.dispose();
      if (renderer.domElement.parentElement === mount) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, [url]);

  return (
    <div className="cad-viewer">
      <div
        ref={mountRef}
        className="cad-viewer-canvas"
        role="img"
        aria-label="Interactive 3D CAD viewport of the generated geometry artifact"
      />
      {status === "loading" ? <p className="empty-state">Loading geometry artifact…</p> : null}
      {status === "error" ? (
        <p className="notice notice-error">The geometry artifact could not be loaded.</p>
      ) : null}
      {status === "unavailable" ? (
        <p className="notice notice-warning">
          <strong>3D view unavailable</strong>
          <span>
            This browser could not create a WebGL context, so the geometry cannot be rendered
            here. The STL artifact is still available for download under Evidence artifacts.
          </span>
        </p>
      ) : null}
      {status === "ready" ? (
        <p className="cad-hint">Drag to orbit · scroll to zoom · right-drag to pan</p>
      ) : null}
    </div>
  );
}
