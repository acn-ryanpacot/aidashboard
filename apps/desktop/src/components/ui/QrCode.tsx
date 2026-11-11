import { encode } from 'uqr';

/** A QR code drawn as SVG squares: offline, no canvas, no innerHTML. */
export function QrCode({ value, label = 'QR code' }: { value: string; label?: string }) {
  const { size, data } = encode(value, { ecc: 'M', border: 2 });
  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      className="size-48 rounded-xl bg-white p-1"
      role="img"
      aria-label={label}
      shapeRendering="crispEdges"
    >
      {data.flatMap((row, y) =>
        row.map((dark, x) =>
          dark ? <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill="#04060b" /> : null,
        ),
      )}
    </svg>
  );
}
