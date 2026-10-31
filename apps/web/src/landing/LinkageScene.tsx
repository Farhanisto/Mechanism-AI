import { useEffect, useRef } from "react";
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

type SceneVariant = "hero" | "showcase";

interface LinkageSceneProps {
  className?: string;
  variant?: SceneVariant;
}

interface Point {
  x: number;
  y: number;
}

function solveCircleIntersection(
  centerA: Point,
  radiusA: number,
  centerB: Point,
  radiusB: number,
): Point | null {
  const dx = centerB.x - centerA.x;
  const dy = centerB.y - centerA.y;
  const distance = Math.hypot(dx, dy);
  if (distance === 0 || distance > radiusA + radiusB) {
    return null;
  }
  if (distance < Math.abs(radiusA - radiusB)) {
    return null;
  }
  const along = (radiusA * radiusA - radiusB * radiusB + distance * distance) / (2 * distance);
  const heightSquared = radiusA * radiusA - along * along;
  if (heightSquared < 0) {
    return null;
  }
  const height = Math.sqrt(heightSquared);
  const midX = centerA.x + (along * dx) / distance;
  const midY = centerA.y + (along * dy) / distance;
  return {
    x: midX - (height * dy) / distance,
    y: midY + (height * dx) / distance,
  };
}

function createGlowTexture(): THREE.Texture {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (context) {
    const gradient = context.createRadialGradient(
      size / 2,
      size / 2,
      0,
      size / 2,
      size / 2,
      size / 2,
    );
    gradient.addColorStop(0, "rgba(120, 225, 255, 0.95)");
    gradient.addColorStop(0.35, "rgba(90, 170, 255, 0.35)");
    gradient.addColorStop(1, "rgba(60, 120, 255, 0)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, size, size);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

function createLinkMaterial(color: number, emissive: number): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color,
    emissive,
    emissiveIntensity: 0.55,
    metalness: 0.82,
    roughness: 0.24,
  });
}

export function LinkageScene({ className = "", variant = "hero" }: LinkageSceneProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) {
      return;
    }

    const reducedMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0.06, variant === "showcase" ? 7.4 : 6.2);
    camera.lookAt(0, 0.02, 0);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    mount.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0x8fa8ff, 1.05));
    const keyLight = new THREE.DirectionalLight(0xdfe9ff, 2.1);
    keyLight.position.set(3.5, 5, 6);
    scene.add(keyLight);
    const cyanLight = new THREE.PointLight(0x38e8ff, 26, 14);
    cyanLight.position.set(-3.6, -1.8, 3.2);
    scene.add(cyanLight);
    const violetLight = new THREE.PointLight(0x9b7bff, 22, 13);
    violetLight.position.set(3.4, 2.4, 2.4);
    scene.add(violetLight);

    const rig = new THREE.Group();
    rig.rotation.x = -0.1;
    scene.add(rig);

    const linkGeometry = new RoundedBoxGeometry(1, 0.22, 0.3, 4, 0.07);
    const linkMaterials = {
      ground: new THREE.MeshStandardMaterial({
        color: 0x1a2337,
        metalness: 0.9,
        roughness: 0.32,
      }),
      crank: createLinkMaterial(0x2f7dff, 0x0c2f7a),
      coupler: createLinkMaterial(0x8b5cf6, 0x2b1168),
      rocker: createLinkMaterial(0x22d3ee, 0x073b44),
    };
    const edgeMaterial = new THREE.LineBasicMaterial({
      color: 0xb9dcff,
      transparent: true,
      opacity: 0.42,
    });

    const makeLink = (material: THREE.MeshStandardMaterial, z: number) => {
      const mesh = new THREE.Mesh(linkGeometry, material);
      mesh.position.z = z;
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(linkGeometry), edgeMaterial);
      mesh.add(edges);
      rig.add(mesh);
      return mesh;
    };

    const groundLink = makeLink(linkMaterials.ground, -0.04);
    const crankLink = makeLink(linkMaterials.crank, 0.02);
    const couplerLink = makeLink(linkMaterials.coupler, 0.06);
    const rockerLink = makeLink(linkMaterials.rocker, 0.02);

    const glowTexture = createGlowTexture();
    const jointMaterial = new THREE.MeshStandardMaterial({
      color: 0xe8f8ff,
      emissive: 0x38e8ff,
      emissiveIntensity: 1.5,
      metalness: 0.1,
      roughness: 0.2,
    });
    const ringMaterial = new THREE.MeshBasicMaterial({
      color: 0x7ee7ff,
      transparent: true,
      opacity: 0.65,
    });
    const jointGeometry = new THREE.SphereGeometry(0.085, 18, 18);
    const ringGeometry = new THREE.TorusGeometry(0.15, 0.018, 10, 40);

    const makeJoint = () => {
      const group = new THREE.Group();
      const core = new THREE.Mesh(jointGeometry, jointMaterial);
      const ring = new THREE.Mesh(ringGeometry, ringMaterial);
      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: glowTexture,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          transparent: true,
          opacity: 0.8,
        }),
      );
      sprite.scale.setScalar(0.95);
      group.add(core, ring, sprite);
      rig.add(group);
      return group;
    };

    const jointA = makeJoint();
    const jointB = makeJoint();
    const jointC = makeJoint();
    const jointD = makeJoint();

    const base = new THREE.Mesh(
      new RoundedBoxGeometry(3.15, 0.16, 0.42, 4, 0.06),
      new THREE.MeshStandardMaterial({ color: 0x121a2b, metalness: 0.85, roughness: 0.35 }),
    );
    base.position.set(0, -0.86, -0.16);
    rig.add(base);

    const pedestalGeometry = new THREE.CylinderGeometry(0.14, 0.18, 0.5, 20);
    const pedestalMaterial = new THREE.MeshStandardMaterial({
      color: 0x1d2a44,
      metalness: 0.8,
      roughness: 0.3,
    });
    for (const x of [-1.18, 1.18]) {
      const pedestal = new THREE.Mesh(pedestalGeometry, pedestalMaterial);
      pedestal.position.set(x, -0.6, -0.08);
      pedestal.rotation.z = Math.PI / 2;
      rig.add(pedestal);
    }

    const particleGeometry = new THREE.BufferGeometry();
    const particleCount = 140;
    const positions = new Float32Array(particleCount * 3);
    for (let index = 0; index < particleCount; index += 1) {
      positions[index * 3] = (Math.random() - 0.5) * 8;
      positions[index * 3 + 1] = (Math.random() - 0.5) * 5;
      positions[index * 3 + 2] = -1.6 - Math.random() * 2.2;
    }
    particleGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const particles = new THREE.Points(
      particleGeometry,
      new THREE.PointsMaterial({
        color: 0x7fb6ff,
        size: 0.02,
        transparent: true,
        opacity: 0.55,
        depthWrite: false,
      }),
    );
    scene.add(particles);

    const anchorA: Point = { x: -1.18, y: -0.44 };
    const anchorD: Point = { x: 1.18, y: -0.44 };
    const crankLength = 0.94;
    const couplerLength = 1.72;
    const rockerLength = 1.16;

    const placeLink = (mesh: THREE.Mesh, start: Point, end: Point) => {
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const length = Math.max(Math.hypot(dx, dy), 0.001);
      mesh.position.x = (start.x + end.x) / 2;
      mesh.position.y = (start.y + end.y) / 2;
      mesh.rotation.z = Math.atan2(dy, dx);
      mesh.scale.x = length;
    };

    const pointer = { x: 0, y: 0 };
    const onPointerMove = (event: PointerEvent) => {
      const bounds = mount.getBoundingClientRect();
      pointer.x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 2;
      pointer.y = ((event.clientY - bounds.top) / bounds.height - 0.5) * 2;
    };
    mount.addEventListener("pointermove", onPointerMove);
    mount.addEventListener("pointerleave", () => {
      pointer.x = 0;
      pointer.y = 0;
    });

    const resize = () => {
      const width = mount.clientWidth || 560;
      const height = mount.clientHeight || 460;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    const clock = new THREE.Clock();
    let frame = 0;
    let rotation = 0;

    const renderPose = (elapsed: number) => {
      const travel = reducedMotion ? 0.5 : 0.5 + 0.5 * Math.sin(elapsed * 0.45);
      const theta = 0.62 + travel * 1.12;
      const crankTip: Point = {
        x: anchorA.x + Math.cos(theta) * crankLength,
        y: anchorA.y + Math.sin(theta) * crankLength,
      };
      const jointPoint =
        solveCircleIntersection(crankTip, couplerLength, anchorD, rockerLength) ?? {
          x: anchorD.x - 0.4,
          y: anchorD.y + rockerLength * 0.8,
        };

      placeLink(groundLink, anchorA, anchorD);
      placeLink(crankLink, anchorA, crankTip);
      placeLink(couplerLink, crankTip, jointPoint);
      placeLink(rockerLink, anchorD, jointPoint);

      jointA.position.set(anchorA.x, anchorA.y, 0.08);
      jointB.position.set(crankTip.x, crankTip.y, 0.1);
      jointC.position.set(jointPoint.x, jointPoint.y, 0.08);
      jointD.position.set(anchorD.x, anchorD.y, 0.08);

      if (!reducedMotion) {
        rotation += 0.0016;
        const driftX = Math.sin(elapsed * 0.35) * 0.06;
        rig.rotation.y += (pointer.x * 0.22 + driftX - rig.rotation.y) * 0.04;
        rig.rotation.x += (-0.1 + pointer.y * 0.1 - rig.rotation.x) * 0.04;
        rig.position.y = Math.sin(elapsed * 0.5) * 0.03;
        particles.rotation.z = rotation * 0.4;
      }
    };

    const animate = () => {
      frame = window.requestAnimationFrame(animate);
      const elapsed = clock.getElapsedTime();
      renderPose(elapsed);
      renderer.render(scene, camera);
    };

    if (reducedMotion) {
      renderPose(0);
      renderer.render(scene, camera);
    } else {
      animate();
    }

    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      mount.removeEventListener("pointermove", onPointerMove);
      scene.traverse((object) => {
        const mesh = object as THREE.Mesh;
        if (mesh.geometry) {
          mesh.geometry.dispose();
        }
        const material = mesh.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(material)) {
          material.forEach((item) => item.dispose());
        } else {
          material?.dispose();
        }
      });
      glowTexture.dispose();
      renderer.dispose();
      if (renderer.domElement.parentElement === mount) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, [variant]);

  return (
    <div
      ref={mountRef}
      className={`linkage-scene ${className}`.trim()}
      role="img"
      aria-label="Animated three-dimensional four-bar linkage model with glowing joints"
    />
  );
}
