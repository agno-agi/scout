"use client";

import { useEffect, useState } from "react";

// Returns true after the component has mounted on the client. Use to gate
// any rendering that depends on browser-only state (localStorage, Intl
// timezone, matchMedia) so the SSR pass renders a stable placeholder and
// React doesn't trip a hydration mismatch.
export function useMounted(): boolean {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}
