"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { Float, MeshDistortMaterial, OrbitControls, Sphere } from "@react-three/drei";
import { useRef } from "react";
import type * as THREE from "three";

/**
 * Rotating glass orb. Visual centerpiece of the hero card. The shader
 * distortion subtly reacts so it doesn't feel static, but stays slow
 * enough to not be distracting on a finance dashboard.
 */
function Orb({ accent }: { accent: string }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((_, delta) => {
    if (!ref.current) return;
    ref.current.rotation.y += delta * 0.15;
    ref.current.rotation.x += delta * 0.06;
  });
  return (
    <Float speed={0.9} rotationIntensity={0.2} floatIntensity={0.6}>
      <Sphere ref={ref} args={[1.2, 96, 96]}>
        <MeshDistortMaterial
          color={accent}
          distort={0.38}
          speed={1.4}
          roughness={0.08}
          metalness={0.85}
          emissive="#3b3b8c"
          emissiveIntensity={0.45}
        />
      </Sphere>
    </Float>
  );
}

export function HeroOrb({ tone = "neutral" }: { tone?: "good" | "bad" | "neutral" }) {
  const accent =
    tone === "good" ? "#10b981" : tone === "bad" ? "#f43f5e" : "#6366f1";
  return (
    <div className="absolute inset-0 -z-10 opacity-90">
      <Canvas
        camera={{ position: [0, 0, 3.4], fov: 50 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true }}
      >
        <ambientLight intensity={0.6} />
        <pointLight position={[3, 3, 5]} intensity={1.2} color="#a5b4fc" />
        <pointLight position={[-4, -2, 3]} intensity={0.6} color="#67e8f9" />
        <Orb accent={accent} />
        <OrbitControls enableZoom={false} enablePan={false} autoRotate autoRotateSpeed={0.4} />
      </Canvas>
    </div>
  );
}
