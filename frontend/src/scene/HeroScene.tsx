/** The landing page's 3D scene: the product's idea as an object.
 *
 *  Video slabs float in depth along a glowing line (the learning path). One slab
 *  is only a dashed outline: a syllabus topic that no video covers. A light
 *  travels the line the way a student moves through the path.
 *
 *  Kept in its own lazily loaded module so three.js never weighs on the app.
 */
import { Float, Line, RoundedBox } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Component, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

type Palette = { bg: string; slab: string; detail: string; accent: string; warn: string };

function readPalette(): Palette {
  const style = getComputedStyle(document.documentElement);
  const value = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    bg: value("--bg", "#0b0c0e"),
    slab: value("--screen", "#1d2025"),
    detail: "#8b9088", // marks on the dark screen, the same in both themes
    accent: value("--accent", "#c8f542"),
    warn: value("--warn", "#ffb454"),
  };
}

const SLAB = { width: 2.1, height: 1.22, depth: 0.07 };
const STOPS = [0.05, 0.21, 0.37, 0.53, 0.69, 0.85, 0.98]; // where slabs sit along the path
const GAP_STOP = 4; // the topic without a video

function usePathCurve() {
  return useMemo(
    () =>
      new THREE.CatmullRomCurve3(
        [
          new THREE.Vector3(-4.4, -1.7, 3.0),
          new THREE.Vector3(-1.5, -0.8, 1.1),
          new THREE.Vector3(1.4, -0.9, -0.8),
          new THREE.Vector3(3.3, 0.3, -2.9),
          new THREE.Vector3(0.7, 1.2, -5.0),
          new THREE.Vector3(-2.5, 1.7, -7.2),
          new THREE.Vector3(0.6, 2.7, -9.6),
        ],
        false,
        "catmullrom",
        0.5,
      ),
    [],
  );
}

const playShape = (() => {
  const shape = new THREE.Shape();
  shape.moveTo(-0.11, -0.14);
  shape.lineTo(0.15, 0);
  shape.lineTo(-0.11, 0.14);
  shape.closePath();
  return shape;
})();

function Slab({ palette, watched }: { palette: Palette; watched: number }) {
  const face = SLAB.depth / 2 + 0.002;
  const barWidth = SLAB.width - 0.36;
  return (
    <group>
      <RoundedBox args={[SLAB.width, SLAB.height, SLAB.depth]} radius={0.05} smoothness={4}>
        <meshStandardMaterial color={palette.slab} roughness={0.42} metalness={0.18} />
      </RoundedBox>
      {/* play mark */}
      <mesh position={[0, 0.1, face]}>
        <shapeGeometry args={[playShape]} />
        <meshBasicMaterial color={palette.accent} toneMapped={false} />
      </mesh>
      {/* title lines */}
      <mesh position={[-0.28, -0.3, face]}>
        <planeGeometry args={[barWidth - 0.56, 0.045]} />
        <meshBasicMaterial color={palette.detail} transparent opacity={0.7} />
      </mesh>
      {/* progress: how much of this video the student has watched */}
      <mesh position={[0, -0.44, face]}>
        <planeGeometry args={[barWidth, 0.022]} />
        <meshBasicMaterial color={palette.detail} transparent opacity={0.35} />
      </mesh>
      {watched > 0 ? (
        <mesh position={[-(barWidth * (1 - watched)) / 2, -0.44, face + 0.001]}>
          <planeGeometry args={[barWidth * watched, 0.022]} />
          <meshBasicMaterial color={palette.accent} toneMapped={false} />
        </mesh>
      ) : null}
    </group>
  );
}

function GhostSlab({ palette }: { palette: Palette }) {
  const w = SLAB.width / 2;
  const h = SLAB.height / 2;
  const outline: [number, number, number][] = [
    [-w, -h, 0],
    [w, -h, 0],
    [w, h, 0],
    [-w, h, 0],
    [-w, -h, 0],
  ];
  return (
    <group>
      <Line points={outline} color={palette.warn} lineWidth={1.6} dashed dashSize={0.14} gapSize={0.1} />
      <mesh>
        <planeGeometry args={[SLAB.width, SLAB.height]} />
        <meshBasicMaterial color={palette.warn} transparent opacity={0.05} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function Scene({ palette, still }: { palette: Palette; still: boolean }) {
  const curve = usePathCurve();
  const rig = useRef<THREE.Group>(null);
  const traveller = useRef<THREE.Group>(null);
  const tube = useMemo(() => new THREE.TubeGeometry(curve, 260, 0.016, 8, false), [curve]);
  useEffect(() => () => tube.dispose(), [tube]);

  const slabs = useMemo(
    () =>
      STOPS.map((stop, index) => {
        const point = curve.getPointAt(stop);
        // Slabs stand just off the line, alternating sides, turned toward the viewer.
        const side = index % 2 === 0 ? 1 : -1;
        return {
          position: new THREE.Vector3(point.x + side * 0.55, point.y + 0.78, point.z),
          anchor: point,
          yaw: -side * 0.28 - point.x * 0.05,
          watched: index < 2 ? 1 : index === 2 ? 0.45 : 0,
        };
      }),
    [curve],
  );

  useFrame((state, delta) => {
    if (rig.current && !still) {
      // The whole sculpture leans a little toward the pointer.
      const targetY = state.pointer.x * 0.16;
      const targetX = -state.pointer.y * 0.08;
      rig.current.rotation.y += (targetY - rig.current.rotation.y) * Math.min(1, delta * 2.5);
      rig.current.rotation.x += (targetX - rig.current.rotation.x) * Math.min(1, delta * 2.5);
    }
    if (traveller.current) {
      const t = still ? 0.4 : (state.clock.elapsedTime * 0.045) % 1;
      traveller.current.position.copy(curve.getPointAt(t));
    }
  });

  return (
    <>
      <fog attach="fog" args={[palette.bg, 8.5, 19]} />
      <ambientLight intensity={0.75} />
      <directionalLight position={[4, 6, 6]} intensity={1.5} />
      <directionalLight position={[-6, 2, -4]} intensity={0.35} />

      <group ref={rig} position={[0.9, -0.5, 0]}>
        <mesh geometry={tube}>
          <meshBasicMaterial color={palette.accent} toneMapped={false} />
        </mesh>

        {slabs.map((slab, index) => (
          <group key={index}>
            <mesh position={slab.anchor}>
              <sphereGeometry args={[0.055, 16, 16]} />
              <meshBasicMaterial
                color={index === GAP_STOP ? palette.warn : palette.accent}
                toneMapped={false}
              />
            </mesh>
            <Float
              speed={still ? 0 : 1.1 + (index % 3) * 0.25}
              rotationIntensity={still ? 0 : 0.22}
              floatIntensity={still ? 0 : 0.55}
            >
              <group position={slab.position} rotation={[0, slab.yaw, 0]}>
                {index === GAP_STOP ? (
                  <GhostSlab palette={palette} />
                ) : (
                  <Slab palette={palette} watched={slab.watched} />
                )}
              </group>
            </Float>
          </group>
        ))}

        <group ref={traveller}>
          <mesh>
            <sphereGeometry args={[0.1, 24, 24]} />
            <meshBasicMaterial color={palette.accent} toneMapped={false} />
          </mesh>
          <pointLight color={palette.accent} intensity={6} distance={4.5} decay={2} />
        </group>
      </group>
    </>
  );
}

/** If WebGL is unavailable the hero simply has no scene; the page still works. */
class SceneBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export default function HeroScene() {
  const [palette, setPalette] = useState(readPalette);
  const [still, setStill] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    const refresh = () => setPalette(readPalette());
    const scheme = window.matchMedia("(prefers-color-scheme: dark)");
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onMotion = () => setStill(motion.matches);
    window.addEventListener("themechange", refresh);
    scheme.addEventListener("change", refresh);
    motion.addEventListener("change", onMotion);
    return () => {
      window.removeEventListener("themechange", refresh);
      scheme.removeEventListener("change", refresh);
      motion.removeEventListener("change", onMotion);
    };
  }, []);

  return (
    <SceneBoundary>
      <Canvas
        aria-hidden
        dpr={[1, 1.75]}
        frameloop={still ? "demand" : "always"}
        camera={{ position: [0.2, 0.5, 8.6], fov: 36, near: 0.1, far: 40 }}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        onCreated={({ camera }) => camera.lookAt(0.6, 0.2, -2.4)}
      >
        <Scene palette={palette} still={still} />
      </Canvas>
    </SceneBoundary>
  );
}
