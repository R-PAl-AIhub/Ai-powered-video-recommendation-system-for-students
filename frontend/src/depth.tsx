/** Depth for ordinary UI: cards that lean toward the pointer, and a floor.
 *
 *  The tilt is driven by Motion values, so pointer movement never re-renders
 *  React. It switches itself off on touch screens (there is no hover to follow)
 *  and when the visitor prefers reduced motion.
 */
import {
  motion,
  useMotionTemplate,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
} from "motion/react";
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";

import { cx } from "./format";

const SPRING = { stiffness: 220, damping: 22, mass: 0.6 };

function useFinePointer(): boolean {
  const [fine, setFine] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(hover: hover) and (pointer: fine)").matches,
  );
  useEffect(() => {
    const query = window.matchMedia("(hover: hover) and (pointer: fine)");
    const onChange = () => setFine(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return fine;
}

const TiltActive = createContext(false);

/** A surface that tilts toward the pointer. Put `Layer`s inside to lift content
 *  above it; the card's own content stays at depth 0. */
export function Tilt({
  children,
  className,
  max = 7, // degrees at the card's edge
  glare = true,
}: {
  children: ReactNode;
  className?: string;
  max?: number;
  glare?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const fine = useFinePointer();
  const active = fine && !reduce;

  // Pointer position over the card, 0..1 on each axis; 0.5 is the centre.
  const px = useMotionValue(0.5);
  const py = useMotionValue(0.5);
  const sx = useSpring(px, SPRING);
  const sy = useSpring(py, SPRING);
  const rotateY = useTransform(sx, [0, 1], [-max, max]);
  const rotateX = useTransform(sy, [0, 1], [max, -max]);
  const glareX = useTransform(sx, [0, 1], [0, 100]);
  const glareY = useTransform(sy, [0, 1], [0, 100]);
  const glareOpacity = useMotionValue(0);
  const sheen = useMotionTemplate`radial-gradient(420px circle at ${glareX}% ${glareY}%, rgb(255 255 255 / 0.10), transparent 60%)`;

  if (!active) {
    return (
      <TiltActive.Provider value={false}>
        <div className={className}>{children}</div>
      </TiltActive.Provider>
    );
  }

  return (
    <TiltActive.Provider value={true}>
      <div className="perspective-scene h-full">
        <motion.div
          ref={ref}
          className={cx("preserve-3d relative will-change-transform", className)}
          style={{ rotateX, rotateY }}
          onPointerMove={(event) => {
            const box = ref.current!.getBoundingClientRect();
            px.set((event.clientX - box.left) / box.width);
            py.set((event.clientY - box.top) / box.height);
            glareOpacity.set(1);
          }}
          onPointerLeave={() => {
            px.set(0.5);
            py.set(0.5);
            glareOpacity.set(0);
          }}
        >
          {children}
          {glare ? (
            <motion.span
              aria-hidden
              className="pointer-events-none absolute inset-0 rounded-[inherit] transition-opacity duration-300"
              style={{ backgroundImage: sheen, opacity: glareOpacity }}
            />
          ) : null}
        </motion.div>
      </div>
    </TiltActive.Provider>
  );
}

/** Content lifted `z` pixels above its tilting card. Flat when the card is not
 *  tilting, so layouts never depend on it. */
export function Layer({
  z = 24,
  children,
  className,
}: {
  z?: number;
  children: ReactNode;
  className?: string;
}) {
  const active = useContext(TiltActive);
  return (
    <div
      className={cx(active && "preserve-3d", className)}
      style={active ? { transform: `translateZ(${z}px)` } : undefined}
    >
      {children}
    </div>
  );
}

/** A receding grid floor fixed behind a page: gives every screen a horizon.
 *  Pure CSS; see `.depth-floor` in styles.css. */
export function DepthFloor() {
  return <div aria-hidden className="depth-floor" />;
}
