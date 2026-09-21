import { useEffect, useState } from "react";

export function useCountUp(target, duration = 600) {
  const [value, setValue] = useState(0);

  useEffect(() => {
    let start = null;
    let raf;
    const from = 0;
    const to = target || 0;

    function step(timestamp) {
      if (start === null) start = timestamp;
      const progress = Math.min((timestamp - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setValue(Math.round(from + (to - from) * eased));
      if (progress < 1) raf = requestAnimationFrame(step);
    }

    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);

  return value;
}
