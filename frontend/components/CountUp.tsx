"use client";

import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { useEffect, useRef } from "react";

interface Props {
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
  className?: string;
  signed?: boolean;
}

/**
 * Animates a number from its previous value to `value` smoothly.
 * Used for headline stats (NAV, P&L, etc).
 */
export function CountUp({
  value,
  decimals = 2,
  prefix = "",
  suffix = "",
  duration = 1.2,
  signed = false,
  className,
}: Props) {
  const mv = useMotionValue(value);
  const display = useTransform(mv, (v) => {
    const fixed = v.toLocaleString("en-IN", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    const sign = signed && v > 0 ? "+" : "";
    return `${prefix}${sign}${fixed}${suffix}`;
  });

  const prev = useRef(value);
  useEffect(() => {
    const controls = animate(mv, value, {
      duration,
      ease: [0.22, 1, 0.36, 1], // smooth easeOut
    });
    prev.current = value;
    return controls.stop;
  }, [value, duration, mv]);

  return <motion.span className={className}>{display}</motion.span>;
}
