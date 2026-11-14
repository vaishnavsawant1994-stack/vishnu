export function NeuralCore({
  active,
  size = "lg",
}: {
  active?: boolean;
  size?: "sm" | "lg";
}) {
  const compact = size === "sm";
  const dots = compact ? 10 : 16;
  const radius = compact ? 78 : 132;
  return (
    <div
      className={compact ? "relative mx-auto h-36 w-full max-w-sm" : "relative mx-auto h-72 w-full max-w-lg"}
      aria-hidden="true"
    >
      <div className="absolute top-1/2 left-1/2 size-40 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent/25 blur-3xl" />
      <div
        className={
          compact
            ? "absolute top-1/2 left-1/2 size-28 -translate-x-1/2 -translate-y-1/2 rounded-full border border-line"
            : "absolute top-1/2 left-1/2 size-64 -translate-x-1/2 -translate-y-1/2 rounded-full border border-line"
        }
      />
      <div
        className={
          compact
            ? "core-sun absolute top-1/2 left-1/2 size-14 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent"
            : "core-sun absolute top-1/2 left-1/2 size-24 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent"
        }
      />
      <div
        className={
          compact
            ? "absolute top-1/2 left-1/2 size-6 -translate-x-1/2 -translate-y-1/2 rounded-full bg-fg"
            : "absolute top-1/2 left-1/2 size-9 -translate-x-1/2 -translate-y-1/2 rounded-full bg-fg"
        }
      />
      <div
        className="absolute inset-0 motion-safe:animate-spin"
        style={{ animationDuration: active ? "12s" : "26s" }}
      >
        {Array.from({ length: dots }, (_, i) => {
          const turn = (i / dots) * 360;
          return (
            <span
              key={i}
              className="absolute top-1/2 left-1/2 block size-2 rounded-full bg-accent"
              style={{
                transform: `translate(-50%, -50%) rotate(${turn}deg) translateX(${radius}px)`,
              }}
            />
          );
        })}
      </div>
    </div>
  );
}
