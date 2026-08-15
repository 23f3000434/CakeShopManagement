import { useEffect, useState } from "react";
import { Icon } from "./Icon";

/**
 * A small, resilient product-photo surface. Product names remain adjacent to
 * every use, so the image stays decorative for assistive technology.
 */
export function CakeImage({ product, className = "", alt = "" }) {
  const source = product?.image_url?.trim() || "";
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => setUnavailable(false), [source]);

  return (
    <span className={`cake-image ${className}`.trim()}>
      {source && !unavailable ? (
        <img src={source} alt={alt} onError={() => setUnavailable(true)} />
      ) : (
        <span className="cake-image__fallback" aria-hidden="true"><Icon name="cake" size={18} /></span>
      )}
    </span>
  );
}
