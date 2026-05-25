/**
 * Viewport-size hook.
 *
 * Returns the current viewport width + a few common breakpoint booleans.
 * Components that need to render different layouts on mobile vs. desktop
 * (split-pane → tabs, table → cards, etc.) should consume this instead of
 * sprinkling raw window.matchMedia calls.
 *
 * Breakpoints align with Tailwind's defaults:
 *   sm  ≥ 640px
 *   md  ≥ 768px
 *   lg  ≥ 1024px
 *   xl  ≥ 1280px
 *
 *   isMobile   — viewport < 768
 *   isTablet   — 768 ≤ viewport < 1024
 *   isDesktop  — viewport ≥ 1024
 */
import { useEffect, useState } from 'react';

export type Viewport = {
  width: number;
  height: number;
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
};

function read(): Viewport {
  // SSR / Electron-pre-mount guard — fall back to a desktop default.
  if (typeof window === 'undefined') {
    return { width: 1280, height: 800, isMobile: false, isTablet: false, isDesktop: true };
  }
  const w = window.innerWidth;
  const h = window.innerHeight;
  return {
    width: w,
    height: h,
    isMobile: w < 768,
    isTablet: w >= 768 && w < 1024,
    isDesktop: w >= 1024,
  };
}

export function useViewport(): Viewport {
  const [vp, setVp] = useState<Viewport>(read);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    let raf = 0;
    function onResize() {
      // Coalesce bursts of resize events (window dragging) into a single
      // setState per animation frame so heavy children don't re-render 60×.
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setVp(read()));
    }
    window.addEventListener('resize', onResize, { passive: true });
    window.addEventListener('orientationchange', onResize, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('orientationchange', onResize);
    };
  }, []);

  return vp;
}
